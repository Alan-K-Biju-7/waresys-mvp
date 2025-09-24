import os
import logging
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, func
from typing import List,Optional
from .config import settings
from .db import SessionLocal, init_db
from . import crud, models, schemas
from .tasks import celery_app
from .stock import confirm_bill
from datetime import date
from app.presentation_adapter import router as presentation_router


app = FastAPI(title="Waresys MVP", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # for the demo, file:// or any origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(presentation_router)
logger = logging.getLogger(__name__)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _startup():
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    init_db()

@app.get("/")
def root():
    return {"ok": True, "docs": "/docs"}

# ------------------- PRODUCTS -------------------
@app.post("/products", response_model=schemas.ProductOut)
def create_product(p: schemas.ProductIn, db: Session = Depends(get_db)):
    return crud.create_product(db, **p.model_dump())

@app.get("/products", response_model=List[schemas.ProductOut])
def list_products(q: str | None = None, db: Session = Depends(get_db)):
    if q:
        return crud.search_products_by_name(db, q)
    return db.query(models.Product).limit(100).all()

# ------------------- BILLS -------------------
@app.post("/bills/ocr", response_model=schemas.OCRResult)
def upload_invoice(
    file: UploadFile = File(...),
    party_name: str | None = Form(None),
    bill_no: str | None = Form(None),
    bill_date: str | None = Form(None),
    db: Session = Depends(get_db)
):
    dest_path = os.path.join(settings.UPLOAD_DIR, file.filename)
    with open(dest_path, "wb") as f:
        f.write(file.file.read())

    # Build BillCreate schema
    bill_in = schemas.BillCreate(
        bill_type="PURCHASE",
        party_name=party_name,
        bill_no=bill_no or file.filename,
        bill_date=bill_date or str(date.today()),   # fallback to today
        source="OCR",
        status="PENDING",
        uploaded_doc=dest_path
)

    result = crud.create_bill(db, bill_in)

    if result.get("duplicate"):
        raise HTTPException(
            status_code=409,
            detail=result["message"]
        )

    bill = result["bill"]

    if result.get("created"):
        celery_app.send_task("process_invoice", args=[bill.id, dest_path])

    return schemas.OCRResult(
        bill_id=bill.id,
        party_name=party_name,
        bill_no=bill_no,
        bill_date=bill_date,
        lines=[],
        needs_review=False,
        message="Invoice accepted. Parsing in background. Poll /bills/{id}."
    )


@app.put("/bills/{bill_id}", response_model=schemas.OCRResult)
def update_bill(
    bill_id: int,
    file: UploadFile = File(...),
    party_name: str | None = Form(None),
    bill_no: str | None = Form(None),
    bill_date: str | None = Form(None),
    db: Session = Depends(get_db)
):
    dest_path = os.path.join(settings.UPLOAD_DIR, file.filename)
    with open(dest_path, "wb") as f:
        f.write(file.file.read())

    bill_in = schemas.BillCreate(
        bill_type="PURCHASE",
        party_name=party_name,
        bill_no=bill_no or file.filename,
        bill_date=bill_date or str(date.today()),   # fallback to today
        source="OCR",
        status="PENDING",
        uploaded_doc=dest_path
)

    result = crud.create_bill(db, bill_in, allow_update=True)
    bill = result["bill"]

    celery_app.send_task("process_invoice", args=[bill.id, dest_path])

    return schemas.OCRResult(
        bill_id=bill.id,
        party_name=party_name,
        bill_no=bill_no,
        bill_date=bill_date,
        lines=[],
        needs_review=False,
        message="Invoice updated. Parsing in background. Poll /bills/{id}."
    )



@app.get("/bills/{bill_id}", response_model=schemas.BillOut)
def get_bill(bill_id: int, db: Session = Depends(get_db)):
    bill = db.get(models.Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Bill not found")

    # Attach lines + review check
    bill.lines = db.query(models.BillLine).filter_by(bill_id=bill_id).all()
    review = db.query(models.ReviewQueue).filter_by(bill_id=bill_id, status="OPEN").first()
    bill.needs_review = bool(review)

    return bill


@app.post("/bills/{bill_id}/confirm")
def confirm(bill_id: int, req: schemas.ConfirmRequest, db: Session = Depends(get_db)):
    review = db.query(models.ReviewQueue).filter_by(bill_id=bill_id, status="OPEN").first()
    if review:
        raise HTTPException(400, "Resolve review items before confirming")
    confirm_bill(db, bill_id=bill_id, bill_type=req.bill_type.upper())
    return {"ok": True, "bill_id": bill_id, "status": "CONFIRMED"}

# ------------------- STOCK -------------------
@app.get("/stock/low")
def low_stock(db: Session = Depends(get_db)):
    return crud.low_stock(db)

# ------------------- GLOBAL ERROR HANDLER -------------------
@app.exception_handler(IntegrityError)
def integrity_error_handler(request, exc: IntegrityError):
    logger.error(f"IntegrityError at {request.url}: {exc}")

    if "uq_party_billno" in str(exc.orig):
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": "DUPLICATE_BILL", "detail": "Bill with this party and bill number already exists."}
        )

    return JSONResponse(
        status_code=400,
        content={"ok": False, "error": "DB_ERROR", "detail": "Database integrity error."}
    )

@app.post("/vendors", response_model=schemas.VendorOut)
def create_vendor(v: schemas.VendorCreate, db: Session = Depends(get_db)):
    return crud.create_vendor(db, v)

@app.get("/vendors", response_model=List[schemas.VendorOut])
def list_vendors(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_vendors(db, skip=skip, limit=limit)

@app.get("/vendors/{vendor_id}", response_model=schemas.VendorOut)
def get_vendor(vendor_id: int, db: Session = Depends(get_db)):
    vendor = crud.get_vendor(db, vendor_id)
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    return vendor
# ----------------- Review Queue Endpoints -----------------

@app.get("/reviews", response_model=List[schemas.ReviewOut])
def list_reviews(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_reviews(db, skip=skip, limit=limit)

@app.get("/reviews/{review_id}", response_model=schemas.ReviewOut)
def get_review(review_id: int, db: Session = Depends(get_db)):
    review = crud.get_review(db, review_id)
    if not review:
        raise HTTPException(404, "Review not found")
    return review

@app.post("/reviews/{review_id}/resolve", response_model=schemas.ReviewOut)
def resolve_review(review_id: int, req: schemas.ReviewResolve, db: Session = Depends(get_db)):
    review = crud.resolve_review(db, review_id, req.notes)
    if not review:
        raise HTTPException(404, "Review not found")
    return review

@app.get("/ping")
def ping(db: Session = Depends(get_db)):
    """
    Health check endpoint.
    Verifies API is running and DB connection works.
    """
    try:
        db.execute(text("SELECT 1"))   # ✅ wrap in text()
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": str(e)}

# ===== Auto-added routes to match frontend =====

@app.post("/bills/upload", response_model=schemas.OCRResult)
def upload_invoice_alias(
    file: UploadFile = File(...),
    party_name: str | None = Form(None),
    bill_no: str | None = Form(None),
    bill_date: str | None = Form(None),
    db: Session = Depends(get_db)
):
    # Delegate to existing /bills/ocr logic
    return upload_invoice(file=file, party_name=party_name, bill_no=bill_no, bill_date=bill_date, db=db)


@app.get("/bills", response_model=List[schemas.BillOut])
def list_bills(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    bills = db.query(models.Bill).order_by(models.Bill.id.desc()).offset(skip).limit(limit).all()
    for b in bills:
        try:
            b.lines = db.query(models.BillLine).filter_by(bill_id=b.id).all()
        except Exception:
            pass
        try:
            review = db.query(models.ReviewQueue).filter_by(bill_id=b.id, status="OPEN").first()
            b.needs_review = bool(review)
        except Exception:
            pass
    return bills


@app.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    products_total = db.query(models.Product).count()
    stock_total_qty = db.query(func.coalesce(func.sum(models.Product.stock_qty), 0)).scalar() or 0

    try:
        bills_processed = db.query(models.Bill).filter(models.Bill.status == "PROCESSED").count()
        bills_pending   = db.query(models.Bill).filter(models.Bill.status != "PROCESSED").count()
    except Exception:
        bills_processed = 0
        bills_pending = 0

    try:
        rows = db.query(
            models.Product.category,
            func.coalesce(func.sum(models.Product.stock_qty), 0).label("qty")
        ).group_by(models.Product.category)         .order_by(func.sum(models.Product.stock_qty).desc())         .limit(6).all()
        category_breakdown = [{"category": r[0] or "Uncategorized", "qty": int(r[1] or 0)} for r in rows]
    except Exception:
        category_breakdown = []

    return {
        "products_total": int(products_total or 0),
        "stock_total_qty": int(stock_total_qty or 0),
        "bills_processed": int(bills_processed or 0),
        "bills_pending": int(bills_pending or 0),
        "category_breakdown": category_breakdown
    }


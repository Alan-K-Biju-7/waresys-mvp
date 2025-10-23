# app/main.py
import os
import logging
from datetime import date
from app.auth import router as auth_router


from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, func, or_
from typing import List

from .config import settings
from .db import SessionLocal, init_db
from . import crud, models, schemas
from .tasks import celery_app                     # <- same celery app the worker uses
from app.presentation_adapter import router as presentation_router

# OPTIONAL: if you want to protect routes, you can import the auth router
# from app.auth import router as auth_router, get_current_user

logger = logging.getLogger(__name__)

TASK_NAME = os.getenv("OCR_TASK_NAME", "app.tasks.process_invoice")
OCR_SYNC = os.getenv("OCR_SYNC", "0") == "1"      # set to "1" to process inline during swagger demos

app = FastAPI(title="Waresys MVP", version="1.0")
@app.get("/api/health")
def api_health():
    return {"ok": True, "service": "waresys-api"}

app.include_router(auth_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# include routers
app.include_router(presentation_router)
# app.include_router(auth_router)   # uncomment if you want auth endpoints mounted here

# ------------------- DB session dep -------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
def _maybe_run_inline_ocr(db: Session, bill: models.Bill, file_path: str) -> bool:
    """
    Try to run OCR inline (fallback). Returns True if it ran.
    """
    try:
        from app.ocr_pipeline import process_invoice as inline_process
        inline_process(file_path, db, bill.id)
        return True
    except Exception:
        logger.exception("[inline OCR] failed")
        return False

@app.post("/bills/ocr", response_model=schemas.OCRResult)
def upload_invoice(
    file: UploadFile = File(...),
    party_name: str | None = Form(None),
    bill_no: str | None = Form(None),
    bill_date: str | None = Form(None),
    db: Session = Depends(get_db),
):
    dest_path = os.path.join(settings.UPLOAD_DIR, file.filename)
    with open(dest_path, "wb") as f:
        f.write(file.file.read())

    bill_in = schemas.BillCreate(
        bill_type="PURCHASE",
        party_name=party_name,
        bill_no=bill_no or file.filename,
        bill_date=bill_date or str(date.today()),
        source="OCR",
        status="PENDING",
        uploaded_doc=dest_path,
    )

    result = crud.create_bill(db, bill_in)
    if result.get("duplicate"):
        raise HTTPException(status_code=409, detail=result["message"])

    bill: models.Bill = result["bill"]

    # enqueue or run inline
    enqueued = False
    if not OCR_SYNC:
        try:
            celery_app.send_task(TASK_NAME, args=[bill.id, dest_path])
            enqueued = True
        except Exception as e:
            logger.warning("Celery enqueue failed (%s). Falling back to inline OCR.", e)

    ran_inline = False
    if not enqueued:
        ran_inline = _maybe_run_inline_ocr(db, bill, dest_path)

    return schemas.OCRResult(
        bill_id=bill.id,
        party_name=party_name,
        bill_no=bill_no,
        bill_date=bill_date,
        lines=[],
        needs_review=False,
        message="Parsed inline." if ran_inline else "Invoice accepted. Parsing in background. Fetch /bills/{id}.",
    )

@app.put("/bills/{bill_id}", response_model=schemas.OCRResult)
def update_bill(
    bill_id: int,
    file: UploadFile = File(...),
    party_name: str | None = Form(None),
    bill_no: str | None = Form(None),
    bill_date: str | None = Form(None),
    db: Session = Depends(get_db),
):
    dest_path = os.path.join(settings.UPLOAD_DIR, file.filename)
    with open(dest_path, "wb") as f:
        f.write(file.file.read())

    bill_in = schemas.BillCreate(
        bill_type="PURCHASE",
        party_name=party_name,
        bill_no=bill_no or file.filename,
        bill_date=bill_date or str(date.today()),
        source="OCR",
        status="PENDING",
        uploaded_doc=dest_path,
    )

    result = crud.create_bill(db, bill_in, allow_update=True)
    bill: models.Bill = result["bill"]

    # enqueue or run inline
    enqueued = False
    if not OCR_SYNC:
        try:
            celery_app.send_task(TASK_NAME, args=[bill.id, dest_path])
            enqueued = True
        except Exception as e:
            logger.warning("Celery enqueue failed (%s). Falling back to inline OCR.", e)

    ran_inline = False
    if not enqueued:
        ran_inline = _maybe_run_inline_ocr(db, bill, dest_path)

    return schemas.OCRResult(
        bill_id=bill.id,
        party_name=party_name,
        bill_no=bill_no,
        bill_date=bill_date,
        lines=[],
        needs_review=False,
        message="Parsed inline." if ran_inline else "Invoice updated. Parsing in background. Fetch /bills/{id}.",
    )

@app.get("/bills/{bill_id}", response_model=schemas.BillOut)
def get_bill(bill_id: int, db: Session = Depends(get_db)):
    bill = db.get(models.Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Bill not found")

    bill.lines = db.query(models.BillLine).filter_by(bill_id=bill_id).all()
    review = db.query(models.ReviewQueue).filter_by(bill_id=bill_id, status="OPEN").first()
    bill.needs_review = bool(review)
    return bill

@app.post("/bills/{bill_id}/confirm")
def confirm(bill_id: int, req: schemas.ConfirmRequest, db: Session = Depends(get_db)):
    review = db.query(models.ReviewQueue).filter_by(bill_id=bill_id, status="OPEN").first()
    if review:
        raise HTTPException(400, "Resolve review items before confirming")
    from .stock import confirm_bill
    confirm_bill(db, bill_id=bill_id, bill_type=req.bill_type.upper())
    return {"ok": True, "bill_id": bill_id, "status": "CONFIRMED"}

# ------------------- STOCK -------------------
@app.get("/stock/low")
def low_stock(db: Session = Depends(get_db)):
    return crud.low_stock(db) if hasattr(crud, "low_stock") else []

# ------------------- GLOBAL ERROR HANDLER -------------------
@app.exception_handler(IntegrityError)
def integrity_error_handler(request, exc: IntegrityError):
    logger.error(f"IntegrityError at {request.url}: {exc}")
    if "uq_party_billno" in str(exc.orig):
        return JSONResponse(status_code=409, content={"ok": False, "error": "DUPLICATE_BILL", "detail": "Bill with this party and bill number already exists."})
    return JSONResponse(status_code=400, content={"ok": False, "error": "DB_ERROR", "detail": "Database integrity error."})

# --------- Vendors & lists (unchanged) ----------
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
@app.get("/search")
def global_search(q: str, db: Session = Depends(get_db)):
    """
    Lightweight global search used by the UI:
      - bills: bill_no / party_name
      - products: name / category
      - vendors: name
    """
    query = (q or "").strip()
    if not query:
        return {"bills": [], "products": [], "vendors": []}

    like = f"%{query}%"

    # Bills
    bills = (
        db.query(models.Bill)
          .filter(or_(
              models.Bill.bill_no.ilike(like),
              models.Bill.party_name.ilike(like),
          ))
          .order_by(models.Bill.id.desc())
          .limit(10)
          .all()
    )
    bills_out = [
        {
            "id": b.id,
            "bill_no": b.bill_no,
            "party_name": b.party_name,
            "bill_date": str(b.bill_date) if getattr(b, "bill_date", None) else None,
            "type": "bill",
        } for b in bills
    ]

    # Products (avoid ILIKE on numeric HSN to keep it portable)
    products = (
        db.query(models.Product)
          .filter(or_(
              models.Product.name.ilike(like),
              models.Product.category.ilike(like),
          ))
          .order_by(models.Product.id.desc())
          .limit(10)
          .all()
    )
    products_out = [
        {
            "id": p.id,
            "name": getattr(p, "name", None),
            "category": getattr(p, "category", None),
            "hsn": getattr(p, "hsn", None),
            "type": "product",
        } for p in products
    ]

    # Vendors
    vendors = (
        db.query(models.Vendor)
          .filter(models.Vendor.name.ilike(like))
          .order_by(models.Vendor.id.desc())
          .limit(10)
          .all()
    )
    vendors_out = [
        {"id": v.id, "name": v.name, "type": "vendor"} for v in vendors
    ]

    return {"bills": bills_out, "products": products_out, "vendors": vendors_out}

@app.get("/ping")
def ping(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": str(e)}

# Aliases / lists / dashboard (unchanged from your version) ...
@app.post("/bills/upload", response_model=schemas.OCRResult)
def upload_invoice_alias(
    file: UploadFile = File(...),
    party_name: str | None = Form(None),
    bill_no: str | None = Form(None),
    bill_date: str | None = Form(None),
    db: Session = Depends(get_db),
):
    return upload_invoice(file=file, party_name=party_name, bill_no=bill_no, bill_date=bill_date, db=db)

@app.get("/bills", response_model=List[schemas.BillOut])
def list_bills(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    bills = db.query(models.Bill).order_by(models.Bill.id.desc()).offset(skip).limit(limit).all()
    for b in bills:
        try:
            b.lines = db.query(models.BillLine).filter_by(bill_id=b.id).all()
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
        rows = (
            db.query(
                models.Product.category,
                func.coalesce(func.sum(models.Product.stock_qty), 0).label("qty")
            )
            .group_by(models.Product.category)
            .order_by(func.sum(models.Product.stock_qty).desc())
            .limit(6)
            .all()
        )
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


import os
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
from .config import settings
from .db import SessionLocal, init_db
from . import crud, models, schemas
from .tasks import celery_app
from .stock import confirm_bill

app = FastAPI(title="Waresys MVP", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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

@app.post("/products", response_model=schemas.ProductOut)
def create_product(p: schemas.ProductIn, db: Session = Depends(get_db)):
    return crud.create_product(db, **p.model_dump())

@app.get("/products", response_model=List[schemas.ProductOut])
def list_products(q: str | None = None, db: Session = Depends(get_db)):
    if q:
        return crud.search_products_by_name(db, q)
    return db.query(models.Product).limit(100).all()

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

    bill = crud.create_bill(
        db,
        bill_type="PURCHASE",
        party_name=party_name,
        bill_no=bill_no or file.filename,
        bill_date=bill_date or "2024-01-01",
        source="OCR",
        status="PENDING",
        uploaded_doc=dest_path
    )

    celery_app.send_task("process_invoice", args=[bill.id, dest_path])

    return schemas.OCRResult(
        bill_id=bill.id, party_name=party_name, bill_no=bill_no, bill_date=bill_date,
        lines=[], needs_review=False, message="Invoice accepted. Parsing in background. Poll /bills/{id}."
    )

@app.get("/bills/{bill_id}")
def get_bill(bill_id: int, db: Session = Depends(get_db)):
    b = db.get(models.Bill, bill_id)
    if not b:
        raise HTTPException(404, "Bill not found")
    lines = db.query(models.BillLine).filter_by(bill_id=bill_id).all()
    review = db.query(models.ReviewQueue).filter_by(bill_id=bill_id, status="OPEN").first()
    return {
        "bill": {"id": b.id, "bill_no": b.bill_no, "bill_date": str(b.bill_date), "status": b.status, "source": b.source, "party_name": b.party_name},
        "lines": [{
            "id": ln.id, "product_id": ln.product_id, "description_raw": ln.description_raw,
            "qty": float(ln.qty),
            "unit_price": float(ln.unit_price) if ln.unit_price else None,
            "conf": float(ln.ocr_confidence) if ln.ocr_confidence is not None else 0
        } for ln in lines],
        "needs_review": bool(review)
    }

@app.post("/bills/{bill_id}/confirm")
def confirm(bill_id: int, req: schemas.ConfirmRequest, db: Session = Depends(get_db)):
    review = db.query(models.ReviewQueue).filter_by(bill_id=bill_id, status="OPEN").first()
    if review:
        raise HTTPException(400, "Resolve review items before confirming")
    confirm_bill(db, bill_id=bill_id, bill_type=req.bill_type.upper())
    return {"ok": True, "bill_id": bill_id, "status": "CONFIRMED"}

@app.get("/stock/low")
def low_stock(db: Session = Depends(get_db)):
    return crud.low_stock(db)

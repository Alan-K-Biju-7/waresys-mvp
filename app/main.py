# app/main.py
from __future__ import annotations

import os
import logging
from datetime import date
from typing import List

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from .config import settings
from .db import SessionLocal, init_db
from . import crud, models, schemas
from .stock import confirm_bill
from .presentation_adapter import router as presentation_router

# ✅ import the task function and call .delay()
from app.tasks import process_invoice

app = FastAPI(title="Waresys MVP", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# ------------------- BILLS (OCR upload) -------------------
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

    bill = result["bill"]

    # ✅ enqueue Celery task via .delay()
    if result.get("created"):
        process_invoice.delay(bill.id, dest_path)

    return schemas.OCRResult(
        bill_id=bill.id,
        party_name=party_name,
        bill_no=bill_no,
        bill_date=bill_date,
        lines=[],
        needs_review=False,
        message="Invoice accepted. Parsing in background. Poll /bills/{id}.",
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
    bill = result["bill"]

    # ✅ enqueue Celery task via .delay()
    process_invoice.delay(bill.id, dest_path)

    return schemas.OCRResult(
        bill_id=bill.id,
        party_name=party_name,
        bill_no=bill_no,
        bill_date=bill_date,
        lines=[],
        needs_review=False,
        message="Invoice updated. Parsing in background. Poll /bills/{id}.",
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
    confirm_bill(db, bill_id=bill_id, bill_type=req.bill_type.upper())
    return {"ok": True, "bill_id": bill_id, "status": "CONFIRMED"}


@app.get("/bills", response_model=List[schemas.BillOut])
def list_bills(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    bills = (
        db.query(models.Bill)
        .order_by(models.Bill.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
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


# ------------------- STOCK -------------------
@app.get("/stock/low")
def low_stock(db: Session = Depends(get_db)):
    rows = (
        db.query(
            models.Product.id,
            models.Product.sku,
            models.Product.name,
            models.Product.reorder_point,
            models.Product.stock_qty,
        )
        .filter(models.Product.reorder_point > 0)
        .all()
    )
    return [
        {
            "product_id": r.id,
            "sku": r.sku,
            "name": r.name,
            "on_hand": float(r.stock_qty or 0),
            "reorder_point": float(r.reorder_point or 0),
        }
        for r in rows
        if float(r.stock_qty or 0) < float(r.reorder_point or 0)
    ]


# ------------------- GLOBAL ERROR HANDLER -------------------
@app.exception_handler(IntegrityError)
def integrity_error_handler(request, exc: IntegrityError):
    if "uq_party_billno" in str(exc.orig):
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": "DUPLICATE_BILL"},
        )
    return JSONResponse(
        status_code=400,
        content={"ok": False, "error": "DB_ERROR"},
    )


# ------------------- Dashboard summary -------------------
@app.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    products_total = db.query(models.Product).count()
    stock_total_qty = db.query(func.coalesce(func.sum(models.Product.stock_qty), 0)).scalar() or 0
    bills_processed = db.query(models.Bill).filter(models.Bill.status == "PROCESSED").count()
    bills_pending = db.query(models.Bill).filter(models.Bill.status != "PROCESSED").count()

    rows = (
        db.query(
            models.Product.category,
            func.coalesce(func.sum(models.Product.stock_qty), 0).label("qty"),
        )
        .group_by(models.Product.category)
        .order_by(func.sum(models.Product.stock_qty).desc())
        .limit(6)
        .all()
    )
    category_breakdown = [{"category": r[0] or "Uncategorized", "qty": int(r[1] or 0)} for r in rows]

    return {
        "products_total": int(products_total or 0),
        "stock_total_qty": int(stock_total_qty or 0),
        "bills_processed": int(bills_processed or 0),
        "bills_pending": int(bills_pending or 0),
        "category_breakdown": category_breakdown,
    }

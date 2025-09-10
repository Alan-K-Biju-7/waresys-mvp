from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from . import models,schemas
from typing import Optional


# ---------- Products ----------
def get_product_by_sku(db: Session, sku: str):
    return db.execute(
        select(models.Product).where(models.Product.sku == sku)
    ).scalar_one_or_none()

def search_products_by_name(db: Session, q: str, limit: int = 25):
    pattern = f"%{q}%"
    return db.execute(
        select(models.Product).where(models.Product.name.ilike(pattern)).limit(limit)
    ).scalars().all()

# api/app/crud.py  (in create_product)
def create_product(db: Session, **data):
    if data.get("category_id") in (0, "0", ""):
        data["category_id"] = None
    obj = models.Product(**data)
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


# ---------- Bills & Lines ----------
def create_bill(db: Session, bill_in: schemas.BillCreate, allow_update: bool = False):
    data = bill_in.dict()
    bill_date_raw = data.get("bill_date")

    # ✅ normalize bill_date
    if isinstance(bill_date_raw, str):
        try:
            data["bill_date"] = datetime.strptime(bill_date_raw, "%Y-%m-%d").date()
        except ValueError:
            try:
                # fallback for dd/mm/yyyy or mm/dd/yyyy
                data["bill_date"] = datetime.strptime(bill_date_raw, "%d/%m/%Y").date()
            except ValueError:
                # last resort → today's date
                data["bill_date"] = date.today()
    elif bill_date_raw is None:
        data["bill_date"] = date.today()

    # vendor linking...
    party_name = data.get("party_name")
    vendor_id = None
    if party_name:
        vendor = get_or_create_vendor(db, party_name)
        vendor_id = vendor.id

    bill = models.Bill(vendor_id=vendor_id, **data)
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return {"bill": bill, "created": True}


def add_bill_line(db: Session, **data):
    l = models.BillLine(**data)
    db.add(l); db.commit(); db.refresh(l)
    return l

# ---------- Review Queue ----------
def add_review(db: Session, bill_id: int, issues: Optional[str] = None):
    review = models.ReviewQueue(
        bill_id=bill_id,
        status="OPEN",
        issues=issues or "Requires manual review"
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


# Some parts of your code may call upsert_review_item(); keep a compatible helper:
def upsert_review_item(db: Session, *, bill_id: int, issues: str):
    existing = db.query(models.ReviewQueue).filter_by(bill_id=bill_id, status="OPEN").first()
    if existing:
        existing.issues = issues
    else:
        db.add(models.ReviewQueue(bill_id=bill_id, issues=issues, status="OPEN"))
    db.commit()

# ---------- Stock / Ledger ----------
def add_ledger(db: Session, product_id: int, qty_change: float, txn_type: str,
               ref_bill_id: int | None, notes: str | None = None):
    row = models.StockLedger(
        product_id=product_id, qty_change=qty_change,
        txn_type=txn_type, ref_bill_id=ref_bill_id, notes=notes
    )
    db.add(row); db.commit(); db.refresh(row)
    return row

def product_on_hand(db: Session, product_id: int) -> float:
    total = db.execute(
        select(func.coalesce(func.sum(models.StockLedger.qty_change), 0.0))
        .where(models.StockLedger.product_id == product_id)
    ).scalar_one()
    return float(total or 0.0)

def low_stock(db: Session):
    # Single query to avoid N+1:
    stmt = (
        select(
            models.Product.id,
            models.Product.sku,
            models.Product.name,
            models.Product.reorder_point,
            func.coalesce(func.sum(models.StockLedger.qty_change), 0.0).label("on_hand"),
        )
        .join(models.StockLedger, models.StockLedger.product_id == models.Product.id, isouter=True)
        .where(models.Product.reorder_point > 0)
        .group_by(models.Product.id)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "product_id": r.id,
            "sku": r.sku,
            "name": r.name,
            "on_hand": float(r.on_hand or 0.0),
            "reorder_point": float(r.reorder_point or 0.0),
        }
        for r in rows
        if float(r.on_hand or 0.0) < float(r.reorder_point or 0.0)
    ]
def get_reviews(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.ReviewQueue).filter(models.ReviewQueue.status == "OPEN").offset(skip).limit(limit).all()

def get_review(db: Session, review_id: int):
    return db.query(models.ReviewQueue).filter(models.ReviewQueue.id == review_id).first()

def resolve_review(db: Session, review_id: int, notes: Optional[str] = None):
    review = db.query(models.ReviewQueue).filter(models.ReviewQueue.id == review_id).first()
    if not review:
        return None
    review.status = "RESOLVED"
    if notes:
        review.issues = (review.issues or "") + f" | Resolved Notes: {notes}"
    db.commit()
    db.refresh(review)
    return review

def create_vendor(db: Session, vendor: schemas.VendorCreate):
    db_vendor = models.Vendor(**vendor.dict())
    db.add(db_vendor)
    db.commit()
    db.refresh(db_vendor)
    return db_vendor

def get_vendors(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Vendor).offset(skip).limit(limit).all()

def get_vendor(db: Session, vendor_id: int):
    return db.query(models.Vendor).filter(models.Vendor.id == vendor_id).first()
def get_or_create_vendor(db: Session, name: str):
    vendor = db.query(models.Vendor).filter(models.Vendor.name == name).first()
    if vendor:
        return vendor
    new_vendor = models.Vendor(name=name)
    db.add(new_vendor)
    db.commit()
    db.refresh(new_vendor)
    return new_vendor

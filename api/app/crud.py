from sqlalchemy.orm import Session
from sqlalchemy import select, func
from . import models

def get_product_by_sku(db: Session, sku: str):
    return db.execute(select(models.Product).where(models.Product.sku == sku)).scalar_one_or_none()

def search_products_by_name(db: Session, q: str, limit: int = 25):
    return db.execute(select(models.Product).where(models.Product.name.ilike(f"%{q}%")).limit(limit)).scalars().all()

def create_product(db: Session, **data):
    obj = models.Product(**data); db.add(obj); db.commit(); db.refresh(obj); return obj

def create_bill(db: Session, **data):
    b = models.Bill(**data); db.add(b); db.commit(); db.refresh(b); return b

def add_bill_line(db: Session, **data):
    l = models.BillLine(**data); db.add(l); db.commit(); db.refresh(l); return l

def add_review(db: Session, bill_id: int, issues: str):
    r = models.ReviewQueue(bill_id=bill_id, issues=issues); db.add(r); db.commit(); db.refresh(r); return r

def add_ledger(db: Session, product_id: int, qty_change: float, txn_type: str, ref_bill_id: int | None, notes: str | None = None):
    row = models.StockLedger(product_id=product_id, qty_change=qty_change, txn_type=txn_type, ref_bill_id=ref_bill_id, notes=notes)
    db.add(row); db.commit(); db.refresh(row); return row

def product_on_hand(db: Session, product_id: int) -> float:
    q = db.execute(select(func.coalesce(func.sum(models.StockLedger.qty_change), 0)).where(models.StockLedger.product_id == product_id)).scalar_one()
    return float(q or 0)

def low_stock(db: Session):
    rows = db.execute(select(models.Product).where(models.Product.reorder_point > 0)).scalars().all()
    out = []
    for p in rows:
        on_hand = product_on_hand(db, p.id)
        if on_hand < float(p.reorder_point):
            out.append({"product_id": p.id, "sku": p.sku, "name": p.name, "on_hand": on_hand, "reorder_point": float(p.reorder_point)})
    return out

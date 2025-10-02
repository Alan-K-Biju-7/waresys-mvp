from sqlalchemy.orm import Session
from fastapi import HTTPException
from . import crud, models

def confirm_bill(db: Session, bill_id: int, bill_type: str):
    bill = db.get(models.Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Bill not found")
    if bill.status not in ("PENDING", "PROCESSED"):
        raise HTTPException(400, f"Bill not confirmable (current={bill.status})")
    lines = db.query(models.BillLine).filter_by(bill_id=bill_id).all()
    if not lines:
        raise HTTPException(400, "No lines to confirm")

    try:
        for ln in lines:
            if not ln.product_id:
                crud.add_review(db, bill_id=bill_id, issues=f"Unresolved product: {ln.description_raw}")
                raise HTTPException(400, "Review required: unresolved products found")
            qty = float(ln.qty or 0)
            qty_change = qty if bill_type.upper() == "PURCHASE" else -qty
            crud.add_ledger(db, product_id=ln.product_id, qty_change=qty_change,
                            txn_type=bill_type.upper(), ref_bill_id=bill_id, notes="auto")
        bill.status = "CONFIRMED"
        db.add(bill); db.commit()
    except Exception:
        db.rollback(); raise

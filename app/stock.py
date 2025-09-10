from sqlalchemy.orm import Session
from . import crud, models
from fastapi import HTTPException

def confirm_bill(db: Session, bill_id: int, bill_type: str):
    bill = db.get(models.Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Bill not found")
    if bill.status != "PENDING":
        raise HTTPException(400, f"Bill not pending (current={bill.status})")
    lines = db.query(models.BillLine).filter_by(bill_id=bill_id).all()
    if not lines: raise ValueError("No lines to confirm")
    try:
        for ln in lines:
            if not ln.product_id:
                raise ValueError("Unresolved product in lines; complete review first")
            qty = float(ln.qty)
            qty_change = qty if bill_type == "PURCHASE" else -qty
            crud.add_ledger(db, product_id=ln.product_id, qty_change=qty_change, txn_type=bill_type, ref_bill_id=bill_id, notes="auto")
        bill.status = "CONFIRMED"
        db.add(bill); db.commit()
    except Exception:
        db.rollback(); raise

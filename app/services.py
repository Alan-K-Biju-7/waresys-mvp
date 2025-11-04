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

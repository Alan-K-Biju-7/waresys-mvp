    db: Session = SessionLocal()
    try:
        bill = db.get(models.Bill, bill_id)
        if not bill:
            return {"bill_id": bill_id, "status": "FAILED", "reason": "Bill not found"}
        # main logic continues...

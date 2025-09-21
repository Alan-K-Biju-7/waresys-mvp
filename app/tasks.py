from celery import Celery
from app.db import SessionLocal
from app import models
from app.pipeline import parse_invoice
from app.matching import match_line_to_catalog
from datetime import date

# Celery instance
celery_app = Celery(
    "waresys",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0"
)

@celery_app.task(name="process_invoice")
def process_invoice(bill_id: int, file_path: str):
    db = SessionLocal()
    try:
        bill = db.query(models.Bill).get(bill_id)
        if not bill:
            return {"error": f"Bill {bill_id} not found"}

        # Build product cache from DB
        products_cache = [
            {"id": p.id, "sku": p.sku, "name": p.name}
            for p in db.query(models.Product).all()
        ]

        # Run OCR + parsing
        parsed = parse_invoice(file_path, db, products_cache=products_cache)

        # If no lines detected, mark failed
        if not parsed["lines"]:
            bill.status = "FAILED"
            bill.needs_review = True
            db.commit()
            return {"bill_id": bill_id, "status": "FAILED", "reason": "No lines detected"}

        # Update Bill header fields
        kv = parsed["kv"]
        bill.bill_no = kv.get("bill_no") or bill.bill_no
        bill.bill_date = kv.get("bill_date") or bill.bill_date or date.today()
        bill.total = kv.get("total") or bill.total
        bill.party_name = kv.get("party_name") or bill.party_name

        # Insert BillLines
        for l in parsed["lines"]:
            match = match_line_to_catalog(l, db, products_cache)
            db_line = models.BillLine(
                bill_id=bill.id,
                product_id=match.get("resolved_product_id"),
                description_raw=l.get("description_raw"),
                qty=float(l.get("qty") or 0),
                unit_price=float(l.get("unit_price") or 0),
                line_total=float(l.get("line_total") or 0),
                ocr_confidence=float(l.get("ocr_confidence") or 0),
            )
            db.add(db_line)

        # Finalize Bill status
        bill.status = "PROCESSED"
        bill.needs_review = parsed["needs_review"]

        db.commit()
        return {"bill_id": bill_id, "status": "PROCESSED"}

    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()

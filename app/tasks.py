from celery import Celery
from app.db import SessionLocal
from app import models,crud
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

        # Build product cache from DB
        products_cache = [
            {"id": p.id, "sku": p.sku, "name": p.name}
            for p in db.query(models.Product).all()
        ]

        # Parse invoice
        parsed = parse_invoice(file_path, db, products_cache=products_cache)
        if not parsed["lines"]:
            bill.status = "FAILED"
            bill.needs_review = True
            db.commit()
            return

        # Update Bill key fields
        bill.bill_no = parsed["kv"].get("bill_no") or bill.bill_no or file_path.split("/")[-1]
        bill.bill_date = parsed["kv"].get("bill_date") or bill.bill_date or date.today()
        bill.total = parsed["kv"].get("total") or bill.total
        bill.party_name = parsed["kv"].get("p(arty_name") or bill.party_name

        for l in parsed["lines"]:
            if not l.get("qty"):   # skip invalid line
                continue
            match = match_line_to_catalog(l, db, products_cache)
            db_line = models.BillLine(
                bill_id=bill.id,
                sku=l.get("sku"),
                description_raw=l.get("description_raw"),
                qty=float(l.get("qty")),
                unit_price=float(l.get("unit_price") or 0),
                line_total=float(l.get("line_total") or 0),
                product_id=match.get("resolved_product_id") if match else None,
                ocr_confidence=float(l.get("ocr_confidence") or 0),
            )
            db.add(db_line)



        bill.status = "PROCESSED"
        bill.needs_review = any(
            l.get("ocr_confidence", 1.0) < 0.9 for l in parsed["lines"]
        )

        db.commit()

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

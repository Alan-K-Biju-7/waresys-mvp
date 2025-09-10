from celery import Celery
from .config import settings
from .db import SessionLocal
from . import crud, models
from .pipeline import parse_invoice
from sqlalchemy import select
from .models import BillLine

celery_app = Celery("waresys", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

@celery_app.task(name="process_invoice")
def process_invoice(bill_id: int, file_path: str):
    db = SessionLocal()
    try:
        parsed = parse_invoice(file_path, db, products_cache=[])

        # Check line-level confidence
        needs_review = any(
            (not l.get("resolved_product_id")) or (l.get("match_score", 0) < 0.75)
            for l in parsed["lines"]
        )

        # Merge with global parser flag
        if parsed.get("needs_review", False):
            needs_review = True

        # Insert review if needed
        if needs_review:
            crud.add_review(db, bill_id=bill_id, issues="Low confidence or missing critical fields")

        # TODO: save parsed lines to DB here (not shown in your snippet)
        # After parsing
        for ln in parsed["lines"]:
            db_line = BillLine(
                bill_id=bill_id,
                description_raw=ln["description_raw"],
                qty=ln["qty"],
                unit_price=ln.get("unit_price"),
                line_total=ln.get("line_total"),
                ocr_confidence=ln["ocr_confidence"],
                product_id=None
            )
            db.add(db_line)

        db.commit()

    finally:
        db.close()


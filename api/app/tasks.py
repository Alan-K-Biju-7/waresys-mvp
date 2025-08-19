from celery import Celery
from .config import settings
from .db import SessionLocal
from . import crud, models
from .ocr.pipeline import parse_invoice
from sqlalchemy import select

celery_app = Celery("waresys", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

@celery_app.task(name="process_invoice")
def process_invoice(bill_id: int, file_path: str):
    db = SessionLocal()
    try:
        products = db.execute(select(models.Product)).scalars().all()
        cache = [{"id": p.id, "name": p.name, "sku": p.sku} for p in products]
        parsed = parse_invoice(file_path, db_session=db, products_cache=cache)
        for ln in parsed["lines"]:
            crud.add_bill_line(db, bill_id=bill_id, product_id=ln.get("resolved_product_id"),
                               description_raw=ln["description_raw"], qty=ln["qty"],
                               unit_price=ln.get("unit_price"), line_total=ln.get("line_total"),
                               ocr_confidence=ln.get("ocr_confidence", 0))
        needs_review = any((not l.get("resolved_product_id")) or (l.get("match_score",0) < 0.75) for l in parsed["lines"])
        if needs_review: crud.add_review(db, bill_id=bill_id, issues="Low confidence / unresolved items")
        return {"ok": True, "needs_review": needs_review}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        db.close()

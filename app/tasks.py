# app/tasks.py
from __future__ import annotations

import logging, math, os, re
from datetime import date
from typing import Dict, Any, Optional

from celery import Celery
from sqlalchemy.exc import SQLAlchemyError
from app.db import SessionLocal
from app import models
from app.pipeline import parse_invoice  # your existing parser
try:
    # optional matcher; keep if available
    from app.matching import match_line_to_catalog
except Exception:
    match_line_to_catalog = None

# ---------- Celery app ----------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")
celery_app = Celery("waresys", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------- Guardrails for OCR numbers ----------
MAX_QTY = 1_000_000           # 1 million units is a sensible ceiling
MAX_UNIT_PRICE = 1_000_000    # ₹1,000,000 per unit ceiling
MAX_LINE_TOTAL = 10_000_000   # ₹10,000,000 per line ceiling

BLOCKLIST = re.compile(
    r"(state\s*name|gst|sgst|cgst|igst|code\b|pan\b|cin\b|"
    r"invoice\s*no|invoice\s*date|bill\s*no|po\s*no|"
    r"address|contact|bank|ifsc|subtotal|sub\s*total|"
    r"round\s*off|grand\s*total|total\b)",
    re.IGNORECASE,
)

def _fnum(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isfinite(v):
            return v
    except Exception:
        pass
    return default

def _clean_line(raw: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], str | None]:
    """
    Returns (cleaned_line_or_None, reason_if_skipped)
    """
    desc = (raw.get("description_raw") or "").strip()
    if not desc or BLOCKLIST.search(desc):
        return None, "blocked_by_text"

    qty = _fnum(raw.get("qty"))
    unit = _fnum(raw.get("unit_price"))
    total = _fnum(raw.get("line_total") or qty * unit)

    # zero/negative or absurd ranges → skip
    if qty <= 0 or unit < 0 or total < 0:
        return None, "non_positive_numbers"
    if qty > MAX_QTY or unit > MAX_UNIT_PRICE or total > MAX_LINE_TOTAL:
        return None, "out_of_range"

    # round to DB scales
    cleaned = dict(
        description_raw=desc[:512],  # safety on varchar length if any
        qty=round(qty, 3),
        unit_price=round(unit, 2),
        line_total=round(total, 2),
        ocr_confidence=_fnum(raw.get("ocr_confidence"), 0.0),
    )
    return cleaned, None


# ---------- Task ----------
@celery_app.task(name="app.tasks.process_invoice")
def process_invoice(bill_id: int, file_path: str) -> Dict[str, Any]:
    """
    Parses the uploaded document and writes BillLines safely.
    Any nonsense lines are skipped; bill gets needs_review=True if we skip anything.
    """
    db = SessionLocal()
    skipped = 0
    try:
        bill = db.get(models.Bill, bill_id)
        if not bill:
            return {"bill_id": bill_id, "status": "FAILED", "reason": "Bill not found"}

        # Run your existing parser
        parsed = parse_invoice(file_path, db, products_cache=[
            {"id": p.id, "sku": getattr(p, "sku", None), "name": p.name}
            for p in db.query(models.Product).all()
        ])
        if not parsed:
            bill.status = "FAILED"
            bill.needs_review = True
            db.commit()
            return {"bill_id": bill_id, "status": "FAILED", "reason": "Parser returned empty"}

        # apply top-level KV if present
        kv = parsed.get("kv", {}) or {}
        bill.bill_no = kv.get("bill_no") or bill.bill_no or os.path.basename(file_path)
        bill.bill_date = kv.get("bill_date") or bill.bill_date or date.today()
        bill.total = _fnum(kv.get("total")) or bill.total
        bill.party_name = kv.get("party_name") or bill.party_name
        bill.source = bill.source or "OCR"

        # build lines safely
        good = 0
        for raw in parsed.get("lines") or []:
            cleaned, reason = _clean_line(raw)
            if not cleaned:
                skipped += 1
                continue

            # optional catalog match
            resolved_product_id = None
            if match_line_to_catalog:
                try:
                    m = match_line_to_catalog(raw, db, None)
                    if isinstance(m, dict):
                        resolved_product_id = m.get("resolved_product_id")
                except Exception:
                    pass

            db.add(models.BillLine(
                bill_id=bill.id,
                product_id=resolved_product_id,
                description_raw=cleaned["description_raw"],
                qty=cleaned["qty"],
                unit_price=cleaned["unit_price"],
                line_total=cleaned["line_total"],
                ocr_confidence=cleaned["ocr_confidence"],
            ))
            good += 1

        # finalize bill status
        if good == 0:
            bill.status = "FAILED"
            bill.needs_review = True
            db.commit()
            return {
                "bill_id": bill.id,
                "status": "FAILED",
                "reason": "No valid line items after sanitization",
                "skipped": skipped,
            }

        bill.status = "PROCESSED"
        bill.needs_review = bool(skipped or parsed.get("needs_review"))
        db.commit()
        return {
            "bill_id": bill.id,
            "status": "PROCESSED",
            "lines_saved": good,
            "lines_skipped": skipped,
            "needs_review": bill.needs_review,
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("[process_invoice] DB error")
        # mark bill for review so UI shows it
        try:
            bill = db.get(models.Bill, bill_id)
            if bill:
                bill.status = "FAILED"
                bill.needs_review = True
                db.commit()
        except Exception:
            db.rollback()
        return {"bill_id": bill_id, "status": "FAILED", "error": str(e.__class__.__name__)}

    except Exception as e:
        logger.exception("[process_invoice] failure")
        try:
            bill = db.get(models.Bill, bill_id)
            if bill:
                bill.status = "FAILED"
                bill.needs_review = True
                db.commit()
        except Exception:
            db.rollback()
        return {"bill_id": bill_id, "status": "FAILED", "error": str(e)}

    finally:
        db.close()

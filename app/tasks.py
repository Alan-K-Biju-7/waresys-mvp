# app/tasks.py
from __future__ import annotations

import logging, math, os, re
from datetime import date, datetime
from typing import Dict, Any, Optional

from celery import Celery
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app import models, crud

# ---------- Celery app ----------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://redis:6379/0"))
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://redis:6379/0"))
celery_app = Celery("waresys", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------- Prefer the unified pipeline ----------
try:
    # Single-source pipeline that saves vendor + lines and commits
    from app.ocr_pipeline import process_invoice as pipeline_process  # type: ignore
except Exception:  # pragma: no cover
    pipeline_process = None  # type: ignore

# ---------- Optional legacy/new adapters ----------
try:
    from app.parsing import parse_invoice as legacy_parse_invoice  # type: ignore
except Exception:  # pragma: no cover
    legacy_parse_invoice = None  # type: ignore

try:
    from app.ocr_pipeline import extract_text_from_pdf, parse_invoice_text  # type: ignore
except Exception:  # pragma: no cover
    extract_text_from_pdf = None  # type: ignore
    parse_invoice_text = None     # type: ignore

# ---------- Guardrails ----------
MAX_QTY = 1_000_000
MAX_UNIT_PRICE = 1_000_000
MAX_LINE_TOTAL = 10_000_000

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
    desc = (raw.get("description_raw") or "").strip()
    if not desc or BLOCKLIST.search(desc):
        return None, "blocked_by_text"

    qty = _fnum(raw.get("qty"))
    unit = _fnum(raw.get("unit_price"))
    total = _fnum(raw.get("line_total") or qty * unit)

    if qty <= 0 or unit < 0 or total < 0:
        return None, "non_positive_numbers"
    if qty > MAX_QTY or unit > MAX_UNIT_PRICE or total > MAX_LINE_TOTAL:
        return None, "out_of_range"

    cleaned = dict(
        description_raw=desc[:512],
        qty=round(qty, 3),
        unit_price=round(unit, 2),
        line_total=round(total, 2),
        ocr_confidence=_fnum(raw.get("ocr_confidence"), 0.0),
    )
    return cleaned, None

def _run_parsing_adapter(file_path: str, db: Session) -> Optional[Dict[str, Any]]:
    """
    Returns a dict like:
      {
        "kv": {...},
        "lines": [...],
        "needs_review": bool,
        "vendor": {name, gst_number, address, contact, email}
      }
    using legacy or OCR text parser.
    """
    # Prefer legacy (if present)
    if legacy_parse_invoice:
        try:
            out = legacy_parse_invoice(
                file_path,
                db,
                products_cache=[
                    {"id": p.id, "sku": getattr(p, "sku", None), "name": p.name}
                    for p in db.query(models.Product).all()
                ],
            )
            if out:
                # legacy returns kv/lines/needs_review; ensure vendor key exists
                out.setdefault("vendor", None)
                return out
        except Exception:
            logger.exception("[adapter] legacy_parse_invoice failed; trying OCR pipeline")

    # Fallback: OCR text parser -> build kv/vendor/lines
    if extract_text_from_pdf and parse_invoice_text:
        text = extract_text_from_pdf(file_path)
        parsed2 = parse_invoice_text(text) or {}

        md = parsed2.get("metadata") or {}
        totals = parsed2.get("totals") or {}
        # prefer consignee/buyer as party_name if present
        kv = {
            "bill_no": md.get("invoice_no"),
            "bill_date": md.get("bill_date"),
            "party_name": md.get("party_name") or md.get("vendor_name"),
            "total": totals.get("grand_total"),
        }
        vendor = {
            "name": md.get("vendor_name"),
            "gst_number": md.get("gst_number"),
            "address": md.get("address"),
            "contact": md.get("phone") or md.get("contact"),
            "email": md.get("email"),
        }
        lines = parsed2.get("lines") or []
        needs_review = not bool(lines)
        return {"kv": kv, "lines": lines, "needs_review": needs_review, "vendor": vendor}

    return None

@celery_app.task(name="app.tasks.process_invoice")
def process_invoice(bill_id: int, file_path: str) -> Dict[str, Any]:
    """
    Background parse & persist:
    1) Prefer the unified pipeline (saves vendor + lines).
    2) Else use adapter and also attach vendor safely (no duplicate-name crashes).
    """
    db: Session = SessionLocal()
    try:
        bill = db.get(models.Bill, bill_id)
        if not bill:
            return {"bill_id": bill_id, "status": "FAILED", "reason": "Bill not found"}

        # --- Path 1: single-source pipeline (best) ---
        if pipeline_process:
            try:
                result = pipeline_process(file_path, db, bill_id)
                # pipeline_process commits; reflect final status and return what it produced
                bill = db.get(models.Bill, bill_id)
                return {"bill_id": bill_id, "status": bill.status, **(result or {})}
            except Exception:
                logger.exception("[task] pipeline_process failed; falling back to adapter path")

        # --- Path 2: adapter path (also attach vendor safely) ---
        parsed = _run_parsing_adapter(file_path, db)
        if not parsed:
            bill.status = "FAILED"
            bill.needs_review = True
            db.commit()
            return {"bill_id": bill_id, "status": "FAILED", "reason": "Parser unavailable"}

        kv = parsed.get("kv") or {}
        lines_in = parsed.get("lines") or []

        # Update bill meta
        bill.bill_no = kv.get("bill_no") or bill.bill_no or os.path.basename(file_path)
        bill.total = _fnum(kv.get("total")) or bill.total

        bd = kv.get("bill_date")
        if isinstance(bd, str):
            try:
                bill.bill_date = datetime.fromisoformat(bd).date()
            except Exception:
                bill.bill_date = bill.bill_date or date.today()
        elif bd:
            bill.bill_date = bd
        else:
            bill.bill_date = bill.bill_date or date.today()

        # Attach/merge vendor (SAFE)
        vendor_info = parsed.get("vendor") or {}
        if vendor_info:
            crud.attach_vendor_to_bill(db, bill, vendor_info)

        # Prefer party_name parsed from consignee/buyer; else vendor name; else keep existing
        bill.party_name = kv.get("party_name") or vendor_info.get("name") or bill.party_name
        bill.source = bill.source or "OCR"

        # Build lines safely
        skipped = 0
        good = 0
        for raw in lines_in:
            cleaned, reason = _clean_line(raw)
            if not cleaned:
                skipped += 1
                continue
            db.add(models.BillLine(
                bill_id=bill.id,
                product_id=None,
                description_raw=cleaned["description_raw"],
                qty=cleaned["qty"],
                unit_price=cleaned["unit_price"],
                line_total=cleaned["line_total"],
                ocr_confidence=cleaned["ocr_confidence"],
                **({"uom": raw.get("uom")} if hasattr(models.BillLine, "uom") else {}),
                **({"hsn": raw.get("hsn")} if hasattr(models.BillLine, "hsn") else {}),
            ))
            good += 1

        if good == 0:
            bill.status = "FAILED"
            bill.needs_review = True
            db.commit()
            return {
                "bill_id": bill.id,
                "status": "FAILED",
                "reason": "No valid line items after sanitization",
                "lines_saved": 0,
                "lines_skipped": skipped,
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
        logger.exception("[task] DB error")
        try:
            bill = db.get(models.Bill, bill_id)
            if bill:
                bill.status = "FAILED"
                bill.needs_review = True
                db.commit()
        except Exception:
            db.rollback()
        return {
            "bill_id": bill_id,
            "status": "FAILED",
            "error": e.__class__.__name__,
            "detail": str(e),
        }

    except Exception as e:
        logger.exception("[task] unexpected failure")
        try:
            bill = db.get(models.Bill, bill_id)
            if bill:
                bill.status = "FAILED"
                bill.needs_review = True
                db.commit()
        except Exception:
            db.rollback()
        return {
            "bill_id": bill_id,
            "status": "FAILED",
            "error": e.__class__.__name__,
            "detail": str(e),
        }

    finally:
        db.close()

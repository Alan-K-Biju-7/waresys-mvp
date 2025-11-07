import os
import re
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import models, schemas

# ============================================================
# Duplicate policy for Bills
# ============================================================
DUP_POLICY = os.getenv("DUP_POLICY", "reuse").strip().lower()

# ============================================================
# Vendor classification tokens (positive/negative)
# ============================================================
_POS_VENDOR_TOKENS = re.compile(
    r"(A2Z|BUILDWARES?|TILE|TILES|SANIT|HARDWARE|CERAM|PVT|LTD|LLP|CO\.?|COMPANY|ENTERPRISES?|AGENC(?:Y|IES)|CERAMIC|BATH|SANITARY)",
    re.I,
)
_NEG_ADDRESS_TOKENS = re.compile(
    r"(GROUND|FLOOR|BLDG|BUILDING|ASSOCIATION|MERCHANTS|NEAR|BANK|ROAD|STREET|LANE|POST|PO\b|PIN|STATE|KERALA|EMAIL|PHONE)",
    re.I,
)
_MONTH_TOKEN = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b", re.I)
_INVOICE_CODEISH = re.compile(r"\b[A-Z0-9]{2,}(?:[\/\-][A-Z0-9]{1,}){1,}\b", re.I)
_DATE_TOKEN = re.compile(r"([0-9]{1,2}[-/][A-Za-z]{3}[-/][0-9]{2,4}|[0-9]{2}[-/][0-9]{2}[-/][0-9]{2,4})")
_COMPANY_SUFFIX = re.compile(
    r"\b(PVT\.?\s*LTD\.?|LTD\.?|LLP|CO\.?|COMPANY|ENTERPRISES?|TRADERS?|INDUSTRIES)\b\.?",
    re.I,
)

# ============================================================
# Helpers
# ============================================================
def _merge_field(obj, field: str, value):
    """Set field if new value is non-empty and current value blank/N/A."""
    if value is None:
        return
    if isinstance(value, str) and value.strip() == "":
        return
    old = getattr(obj, field, None)
    if old in (None, "", "N/A"):
        setattr(obj, field, value)
def _digits(s: str | None) -> int:
    return len(re.sub(r"\D", "", s or ""))
def _looks_vendorish(name: str | None) -> bool:
    return bool(name and _POS_VENDOR_TOKENS.search(name) and not _NEG_ADDRESS_TOKENS.search(name))
def _looks_addressish(name: str | None) -> bool:
    return bool(name and _NEG_ADDRESS_TOKENS.search(name) and not _POS_VENDOR_TOKENS.search(name))

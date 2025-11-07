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
def _normalize_contact(contact: Optional[str]) -> Optional[str]:
    """
    Normalize Indian phone numbers to +91XXXXXXXXXX.
    Accepts '04802731800, 9544499430' or '+91 95444 99430'.
    """
    if not contact:
        return contact
    raw = str(contact)
    cand = re.findall(r"(?:\+91[\-\s]?)?\d{10}|\b\d{3,5}[-\s]?\d{6,8}\b", raw)
    uniq: List[str] = []
    seen = set()
    for c in cand:
        d = re.sub(r"\D", "", c)
        if d.startswith("91") and len(d) >= 12:
            d = d[-10:]
        elif len(d) > 10:
            d = d[-10:]
        if len(d) == 10:
            norm = f"+91{d}"
        else:
            norm = f"+{d}" if not d.startswith("0") else d
        key = re.sub(r"\D", "", norm)[-10:]
        if key and key not in seen:
            uniq.append(norm)
            seen.add(key)
    return ", ".join(uniq) if uniq else None
def _canonicalize_vendor_name(name: Optional[str]) -> Optional[str]:
    """
    Clean vendor names: remove address tails, dates, codes, and title-case.
    """
    if not name:
        return name
    s = re.sub(r"\s+", " ", str(name)).strip(" -,/.")

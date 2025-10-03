# app/crud.py
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
#   DUP_POLICY = "reuse" (default) | "suffix" | "error"
# ============================================================
DUP_POLICY = os.getenv("DUP_POLICY", "reuse").strip().lower()

# ============================================================
# Vendor classification tokens (for smart upgrades)
# ============================================================
_POS_VENDOR_TOKENS = re.compile(
    r"(A2Z|BUILDWARES?|TILE|TILES|SANIT|HARDWARE|CERAM|PVT|LTD|LLP|CO\.?|COMPANY|ENTERPRISES?|AGENC(?:Y|IES)|CERAMIC|BATH|SANITARY)",
    re.I,
)
_NEG_ADDRESS_TOKENS = re.compile(
    r"(GROUND|FLOOR|BLDG|BLDGS?|BUILDING|ASSOCIATION|MERCHANTS|NEAR|BANK|ROAD|RD\.?|STREET|ST\.?|LANE|POST|PO\b|PIN|STATE\s*NAME|KORATTY|THRISSUR|KERALA|EMAIL|E[-\s]?MAIL|PHONE)",
    re.I,
)
_MONTH_TOKEN = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|July?|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\b", re.I)
_INVOICE_CODEISH = re.compile(
    r"\b[A-Z0-9]{2,}(?:[\/\-][A-Z0-9]{1,}){1,}\b|\b\d{2,}[\/\-]\d{2,}(?:[\/\-]\d{2,})+\b",
    re.I,
)
_DATE_TOKEN = re.compile(r"([0-9]{1,2}[-/][A-Za-z]{3}[-/][0-9]{2,4}|[0-9]{2}[-/][0-9]{2}[-/][0-9]{2,4})")

_COMPANY_SUFFIX = re.compile(
    r"\b(PVT\.?\s*LTD\.?|PVT|LTD\.?|LLP|CO\.?|COMPANY|ENTERPRISES?|TRADERS?|INDUSTRIES)\b\.?",
    re.I,
)

# ============================================================
# Helpers
# ============================================================
def _merge_field(obj, field: str, value):
    """Only set field if incoming value is non-empty and current value is blank/N/A."""
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
    Normalize Indian phone numbers to +91XXXXXXXXXX, merge unique.
    Accepts strings like '04802731800, 9544499430' or '+91 95444 99430'.
    """
    if not contact:
        return contact
    raw = str(contact)
    # collect candidates (10+ digits patterns, with or without +91)
    cand = re.findall(r"(?:\+91[\-\s]?)?\d{10}|\b\d{3,5}[-\s]?\d{6,8}\b", raw)
    uniq: List[str] = []
    seen = set()
    for c in cand:
        d = re.sub(r"\D", "", c)
        # Strip std code, keep last 10 digits
        if d.startswith("91") and len(d) >= 12:
            d = d[-10:]
        elif len(d) > 10:
            d = d[-10:]
        if len(d) == 10:
            norm = f"+91{d}"
        else:
            # leave as-is if not a mobile-length number
            norm = f"+{d}" if not d.startswith("0") else d
        key = re.sub(r"\D", "", norm)[-10:]
        if key and key not in seen:
            uniq.append(norm)
            seen.add(key)
    return ", ".join(uniq) if uniq else None

def _canonicalize_vendor_name(name: Optional[str]) -> Optional[str]:
    """
    Clean up vendor names:
    - remove addressish tail (NEAR/BANK/...),
    - remove clear dates / invoice-like codes,
    - collapse spaces & punctuation at edges,
    - title-case while preserving common acronyms.
    """
    if not name:
        return name
    s = re.sub(r"\s+", " ", str(name)).strip(" -,/.")

    # cut at first address token if it exists
    m = _NEG_ADDRESS_TOKENS.search(s)
    if m:
        s = s[:m.start()].strip(" -,/.")

    # strip after date/month tokens or invoice-like codes
    s = _DATE_TOKEN.sub("", s)
    s = _INVOICE_CODEISH.sub("", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -,/.")

    if not s:
        return None

    # Title case then restore acronyms and common tokens
    titled = s.title()
    titled = re.sub(r"(?i)\bA\s*2\s*Z\b", "A2Z", titled)
    titled = titled.replace("Llp", "LLP").replace("Pvt", "Pvt").replace("Ltd", "Ltd")
    return titled.strip(" -,/.")

def _name_key_for_match(name: Optional[str]) -> Optional[str]:
    """A loose key to match vendors by name: lowercase, strip punctuation & extra spaces & common suffixes."""
    if not name:
        return None
    s = _canonicalize_vendor_name(name) or ""
    # drop company suffixes for matching
    s = _COMPANY_SUFFIX.sub("", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s or None

def _upgrade_vendor_fields_if_better(vendor, *, name=None, address=None, contact=None, email=None) -> bool:
    """
    If an existing vendor was created with a weak/partial name (e.g., an address line),
    upgrade it when we see a stronger company-like name for the SAME GST or same canonical name.
    """
    changed = False
    if name and _looks_vendorish(name):
        current = getattr(vendor, "name", "") or ""
        # upgrade if current is empty, addressish, or clearly shorter/weaker
        if current in ("", "N/A") or _looks_addressish(current) or len(name) > len(current):
            if _name_key_for_match(name) != _name_key_for_match(current):
                vendor.name = _canonicalize_vendor_name(name)
                changed = True

    # prefer contact with more digits / more unique numbers
    if contact:
        new_c = _normalize_contact(contact) or ""
        old_c = _normalize_contact(getattr(vendor, "contact", "")) or ""
        if _digits(new_c) > _digits(old_c):
            vendor.contact = new_c
            changed = True

    if address and (
        not getattr(vendor, "address", None)
        or (len(address) > len(getattr(vendor, "address", "")) and len(address) < 200)
    ):
        vendor.address = address
        changed = True

    if email and not getattr(vendor, "email", None):
        vendor.email = email.lower()
        changed = True

    return changed

# ============================================================
# Products
# ============================================================
def get_product_by_sku(db: Session, sku: str):
    return db.execute(
        select(models.Product).where(models.Product.sku == sku)
    ).scalar_one_or_none()

def search_products_by_name(db: Session, q: str, limit: int = 25):
    pattern = f"%{q}%"
    return (
        db.execute(
            select(models.Product)
            .where(models.Product.name.ilike(pattern))
            .limit(limit)
        )
        .scalars()
        .all()
    )

def create_product(db: Session, **data):
    if data.get("category_id") in (0, "0", ""):
        data["category_id"] = None
    obj = models.Product(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

# ============================================================
# Vendor helpers (single, authoritative implementation)
# ============================================================
def _find_vendor_by_canonical_name(db: Session, name: Optional[str]):
    """
    Try to find a vendor by a canonicalized, case-insensitive name key.
    """
    if not name:
        return None
    key = _name_key_for_match(name)
    if not key:
        return None
    # Pull a small set and match in python (portable across DBs)
    rows = db.execute(select(models.Vendor).limit(200)).scalars().all()
    for v in rows:
        vk = _name_key_for_match(v.name)
        if vk and vk == key:
            return v
    return None

def get_or_create_vendor(
    db: Session,
    name: Optional[str],
    gst_number: Optional[str] = None,
    address: Optional[str] = None,
    contact: Optional[str] = None,
    email: Optional[str] = None,
):
    """
    Prefer a GST match; else fallback to a canonicalized name match.
    Merge any missing fields, and upgrade clearly-better fields.
    """
    Vendor = models.Vendor

    # Pre-sanitize inputs
    safe_name = _canonicalize_vendor_name(name)
    safe_contact = _normalize_contact(contact)
    safe_email = email.lower() if email else None

    v = None
    if gst_number:
        v = db.execute(select(Vendor).where(Vendor.gst_number == gst_number)).scalars().first()

    if v is None and safe_name:
        v = _find_vendor_by_canonical_name(db, safe_name)

    if v:
        # Merge blanks first (never merge an addressy "name" over a good one)
        if safe_name and _looks_vendorish(safe_name):
            _merge_field(v, "name", safe_name)
        _merge_field(v, "gst_number", gst_number)
        _merge_field(v, "address", address)
        if safe_contact:
            # merge phones preferring longer
            old = _normalize_contact(getattr(v, "contact", ""))
            if _digits(safe_contact) > _digits(old or ""):
                v.contact = safe_contact
        if safe_email and not getattr(v, "email", None):
            v.email = safe_email

        # Attempt smart upgrades if GST matches or we matched by canonical name
        if (gst_number and v.gst_number == gst_number) or (safe_name and _name_key_for_match(v.name) == _name_key_for_match(safe_name)):
            if _upgrade_vendor_fields_if_better(v, name=safe_name, address=address, contact=safe_contact, email=safe_email):
                db.flush()
        return v

    # Create new
    create_name = safe_name if _looks_vendorish(safe_name) else ("Unknown Vendor" if safe_name else "Unknown Vendor")
    v = Vendor(
        name=create_name,
        gst_number=gst_number,
        address=address,
        contact=safe_contact,
        email=safe_email,
    )
    db.add(v)
    db.flush()
    return v

def attach_vendor_to_bill(db: Session, bill: models.Bill, vendor_info: dict | None):
    if not vendor_info:
        return bill
    v = get_or_create_vendor(
        db,
        name=vendor_info.get("name"),
        gst_number=vendor_info.get("gst_number"),
        address=vendor_info.get("address"),
        contact=vendor_info.get("contact"),
        email=vendor_info.get("email"),
    )
    bill.vendor_id = v.id
    return bill

# ============================================================
# Vendors (endpoints support)
# ============================================================
def create_vendor(db: Session, vendor: schemas.VendorCreate):
    # sanitize on manual create as well
    vendor_dict = vendor.dict()
    vendor_dict["name"] = _canonicalize_vendor_name(vendor_dict.get("name"))
    vendor_dict["contact"] = _normalize_contact(vendor_dict.get("contact"))
    if vendor_dict.get("email"):
        vendor_dict["email"] = vendor_dict["email"].lower()
    db_vendor = models.Vendor(**vendor_dict)
    db.add(db_vendor)
    db.commit()
    db.refresh(db_vendor)
    return db_vendor

def get_vendors(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Vendor).offset(skip).limit(limit).all()

def get_vendor(db: Session, vendor_id: int):
    return db.query(models.Vendor).filter(models.Vendor.id == vendor_id).first()

# ============================================================
# Bills & Lines
# ============================================================
def _parse_bill_date(value) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d-%m-%y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return date.today()

def _create_bill_row(db: Session, data: dict, vendor_id: Optional[int]) -> models.Bill:
    bill = models.Bill(
        bill_no=data["bill_no"],
        bill_date=_parse_bill_date(data.get("bill_date")),
        party_name=data.get("party_name"),
        status=data.get("status") or "PENDING",
        source=data.get("source") or "OCR",
        uploaded_doc=data.get("uploaded_doc"),
        vendor_id=vendor_id,
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill

def create_bill(db: Session, bill_in: schemas.BillCreate, allow_update: bool = False):
    """
    Duplicate behavior is controlled by DUP_POLICY (env):
      - reuse  : return existing bill object (no error)
      - suffix : create new bill with bill_no suffixed by -DUP-N
      - error  : return {"duplicate": True, ...} (your /bills/ocr will raise 409)
    NOTE: We no longer create a vendor from party_name here; OCR will attach the true vendor.
    """
    data = bill_in.dict()
    data.pop("bill_type", None)  # not on model
    data["bill_date"] = _parse_bill_date(data.get("bill_date"))

    # Try to find an existing bill for (party_name, bill_no)
    existing = (
        db.query(models.Bill)
        .filter(
            models.Bill.party_name == data.get("party_name"),
            models.Bill.bill_no == data["bill_no"],
        )
        .first()
    )

    vendor_id = None  # vendor will be attached by OCR later

    if existing and not allow_update:
        if DUP_POLICY == "reuse":
            return {"created": False, "duplicate": False, "message": "Duplicate reused", "bill": existing}
        if DUP_POLICY == "suffix":
            count = (
                db.query(models.Bill)
                .filter(
                    models.Bill.party_name == data.get("party_name"),
                    models.Bill.bill_no.like(f"{data['bill_no']}%"),
                )
                .count()
            )
            new_no = f"{data['bill_no']}-DUP-{count + 1}"
            bill = _create_bill_row(db, dict(data, bill_no=new_no), vendor_id)
            return {"created": True, "duplicate": False, "message": f"Duplicate created as {new_no}", "bill": bill}
        return {"duplicate": True, "message": "Duplicate bill exists", "bill": existing}

    if existing and allow_update:
        if data.get("uploaded_doc"):
            existing.uploaded_doc = data["uploaded_doc"]
        if data.get("bill_date"):
            existing.bill_date = data["bill_date"]
        if data.get("party_name"):
            existing.party_name = data["party_name"]
        if vendor_id:
            existing.vendor_id = vendor_id
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return {"created": False, "duplicate": False, "message": "Updated existing bill", "bill": existing}

    bill = _create_bill_row(db, data, vendor_id)
    return {"bill": bill, "created": True, "duplicate": False, "message": "Bill created"}

def add_bill_line(db: Session, **data):
    l = models.BillLine(**data)
    db.add(l)
    db.commit()
    db.refresh(l)
    return l

# ============================================================
# Review Queue
# ============================================================
def add_review(db: Session, bill_id: int, issues: Optional[str] = None):
    review = models.ReviewQueue(
        bill_id=bill_id, status="OPEN", issues=issues or "Requires manual review"
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review

def upsert_review_item(db: Session, *, bill_id: int, issues: str):
    existing = db.query(models.ReviewQueue).filter_by(bill_id=bill_id, status="OPEN").first()
    if existing:
        existing.issues = issues
    else:
        db.add(models.ReviewQueue(bill_id=bill_id, issues=issues, status="OPEN"))
    db.commit()

def get_reviews(db: Session, skip: int = 0, limit: int = 100):
    return (
        db.query(models.ReviewQueue)
        .filter(models.ReviewQueue.status == "OPEN")
        .offset(skip)
        .limit(limit)
        .all()
    )

def get_review(db: Session, review_id: int):
    return db.query(models.ReviewQueue).filter(models.ReviewQueue.id == review_id).first()

def resolve_review(db: Session, review_id: int, notes: Optional[str] = None):
    review = db.query(models.ReviewQueue).filter(models.ReviewQueue.id == review_id).first()
    if not review:
        return None
    review.status = "RESOLVED"
    if notes:
        review.issues = (review.issues or "") + f" | Resolved Notes: {notes}"
    db.commit()
    db.refresh(review)
    return review

# ============================================================
# Stock / Ledger
# ============================================================
def add_ledger(
    db: Session,
    product_id: int,
    qty_change: float,
    txn_type: str,
    ref_bill_id: int | None,
    notes: str | None = None,
):
    row = models.StockLedger(
        product_id=product_id,
        qty_change=qty_change,
        txn_type=txn_type,
        ref_bill_id=ref_bill_id,
        notes=notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

# ============================================================
# Invoices (vendor OCR)
# ============================================================
def create_invoice_with_lines(db: Session, inv: dict) -> models.Invoice:
    invoice = models.Invoice(
        vendor_name=_canonicalize_vendor_name(inv.get("vendor_name")),
        voucher_no=inv.get("voucher_no"),
        invoice_date=inv.get("invoice_date"),
        bill_to=inv.get("bill_to"),
        ship_to=inv.get("ship_to"),
        subtotal=inv.get("subtotal"),
        cgst=inv.get("cgst"),
        sgst=inv.get("sgst"),
        igst=inv.get("igst"),
        other_charges=inv.get("other_charges"),
        total=inv.get("total"),
        raw_text=inv.get("raw_text"),
    )
    for ln in inv.get("lines", []):
        invoice.lines.append(
            models.InvoiceLine(
                description=ln.get("description"),
                hsn=ln.get("hsn"),
                uom=ln.get("uom"),
                qty=ln.get("qty"),
                rate=ln.get("rate"),
                discount_pct=ln.get("discount_pct"),
                amount=ln.get("amount"),
                sku=ln.get("sku"),
            )
        )
    db.add(invoice)
    db.flush()
    return invoice

def upsert_product_and_add_stock(db: Session, desc: str, hsn: str | None, qty):
    prod = db.query(models.Product).filter(models.Product.name.ilike(desc)).first()
    if not prod:
        base = (desc or "SKU").upper().replace(" ", "-")[:10]
        prod = models.Product(
            sku=f"AUTO-{abs(hash(base)) % 10_000_000}",
            name=desc,
            category=None,
            stock_qty=0,
        )
        db.add(prod)
        db.flush()
    prod.stock_qty = (prod.stock_qty or 0) + (qty or 0)
    return prod

def apply_stock_from_invoice(db: Session, invoice: models.Invoice):
    for line in invoice.lines:
        if (line.qty or 0) > 0:
            upsert_product_and_add_stock(db, line.description, line.hsn, line.qty)
    db.commit()

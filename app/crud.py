# app/crud.py
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import Optional
from decimal import Decimal
from . import models, schemas

# ---------- Products ----------
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


# ---------- Vendor helpers (new/expanded) ----------
def _merge_field(obj, field: str, value):
    """Only set field if incoming value is non-empty and current value is blank/N/A."""
    if value is None:
        return
    if isinstance(value, str) and value.strip() == "":
        return
    old = getattr(obj, field, None)
    if old in (None, "", "N/A"):
        setattr(obj, field, value)

def get_or_create_vendor(
    db: Session,
    name: Optional[str],
    gst_number: Optional[str] = None,
    address: Optional[str] = None,
    contact: Optional[str] = None,
    email: Optional[str] = None,
):
    """
    Prefer a GST match; else fallback to a case-insensitive name match.
    Merge any missing fields (address/contact/email) into the existing vendor.
    """
    Vendor = models.Vendor
    vendor = None

    if gst_number:
        vendor = (
            db.query(Vendor)
            .filter(func.lower(Vendor.gst_number) == gst_number.lower())
            .first()
        )

    if not vendor and name:
        vendor = (
            db.query(Vendor)
            .filter(func.lower(Vendor.name) == name.lower())
            .first()
        )

    if not vendor:
        vendor = Vendor(
            name=name or "Unknown Vendor",
            gst_number=gst_number,
            address=address,
            contact=contact,
            email=email,
        )
        db.add(vendor)
        db.flush()  # avoid an early commit; caller can commit

    # Merge newly parsed info into existing record
    if gst_number and not vendor.gst_number:
        vendor.gst_number = gst_number
    _merge_field(vendor, "address", address)
    _merge_field(vendor, "contact", contact)
    _merge_field(vendor, "email", email)

    return vendor

def attach_vendor_to_bill(db: Session, bill: models.Bill, vendor_info: Optional[dict]):
    """
    Given parsed vendor_info, ensure a Vendor exists and set bill.vendor_id.
    vendor_info shape: { name, gst_number, address, contact, email }
    """
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


# ---------- Vendors (existing endpoints support) ----------
def create_vendor(db: Session, vendor: schemas.VendorCreate):
    db_vendor = models.Vendor(**vendor.dict())
    db.add(db_vendor)
    db.commit()
    db.refresh(db_vendor)
    return db_vendor

def get_vendors(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Vendor).offset(skip).limit(limit).all()

def get_vendor(db: Session, vendor_id: int):
    return db.query(models.Vendor).filter(models.Vendor.id == vendor_id).first()


# ---------- Bills & Lines ----------
def create_bill(db: Session, bill_in: schemas.BillCreate, allow_update: bool = False):
    data = bill_in.dict()
    bill_date_raw = data.get("bill_date")

    if isinstance(bill_date_raw, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                data["bill_date"] = datetime.strptime(bill_date_raw, fmt).date()
                break
            except ValueError:
                pass
        if not isinstance(data.get("bill_date"), date):
            data["bill_date"] = date.today()
    elif bill_date_raw is None:
        data["bill_date"] = date.today()

    existing = (
        db.query(models.Bill)
        .filter_by(party_name=data.get("party_name"), bill_no=data["bill_no"])
        .first()
    )
    if existing and not allow_update:
        return {"duplicate": True, "message": "Duplicate bill exists"}

    # Attach a vendor record (basic: by party_name for now; better info can be merged later in tasks)
    vendor_id = None
    party_name = data.get("party_name")
    if party_name:
        v = get_or_create_vendor(db, name=party_name)
        vendor_id = v.id

    bill = models.Bill(vendor_id=vendor_id, **data)
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return {"bill": bill, "created": True}

def add_bill_line(db: Session, **data):
    l = models.BillLine(**data)
    db.add(l)
    db.commit()
    db.refresh(l)
    return l


# ---------- Review Queue ----------
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


# ---------- Stock / Ledger ----------
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


# ---------- Invoices (vendor OCR) ----------
def create_invoice_with_lines(db: Session, inv: dict) -> models.Invoice:
    invoice = models.Invoice(
        vendor_name=inv.get("vendor_name"),
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

# Link/merge vendor info to a Bill (called from Celery after parsing)
def attach_vendor_to_bill(db, bill, vdict: dict | None):
    if not bill or not vdict:
        return bill
    name = (vdict.get("name") or bill.party_name or "").strip()
    if not name:
        return bill

    vendor = db.query(models.Vendor).filter(models.Vendor.name == name).first()
    if not vendor:
        vendor = models.Vendor(name=name)

    # update lightweight fields if present
    if vdict.get("gst_number"):
        vendor.gst_number = vdict["gst_number"]
    if vdict.get("address"):
        vendor.address = vdict["address"]
    if vdict.get("contact"):
        vendor.contact = vdict["contact"]
    if vdict.get("email"):
        vendor.email = vdict["email"]

    db.add(vendor); db.flush()
    bill.vendor_id = vendor.id
    bill.party_name = name
    db.add(bill)
    return bill


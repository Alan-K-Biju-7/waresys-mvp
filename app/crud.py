# app/crud.py
import os
from datetime import datetime, date
from typing import Optional
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import models, schemas

# ============================================================
# Duplicate policy for Bills
#   DUP_POLICY = "reuse" (default) | "suffix" | "error"
#   - reuse  : return existing bill (no 409, good for Swagger testing)
#   - suffix : create a new bill with bill_no suffixed by -DUP-N
#   - error  : strict mode; surface duplicate to the API (your /bills/ocr will 409)
# ============================================================
DUP_POLICY = os.getenv("DUP_POLICY", "reuse").strip().lower()


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
# Vendor helpers
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
            .filter(func.lower(Vendor.name) == (name or "").lower())
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
        db.flush()  # no commit; caller will commit

    # Merge newly parsed info into existing record (avoid unique-name collisions)
    if gst_number and not vendor.gst_number:
        vendor.gst_number = gst_number
    _merge_field(vendor, "address", address)
    _merge_field(vendor, "contact", contact)
    _merge_field(vendor, "email", email)

    return vendor


def attach_vendor_to_bill(db: Session, bill: models.Bill, vendor_info: Optional[dict]):
    """
    Ensure a Vendor exists and set bill.vendor_id.
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


# ============================================================
# Vendors (endpoints support)
# ============================================================
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
    """
    data = bill_in.dict()

    # Bill model has no 'bill_type'
    data.pop("bill_type", None)

    # Normalize date
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

    # Attach vendor up-front (so both new and reused cases have vendor_id)
    vendor_id = None
    party_name = data.get("party_name")
    if party_name:
        v = get_or_create_vendor(db, name=party_name)
        vendor_id = v.id

    # Existing row found
    if existing and not allow_update:
        if DUP_POLICY == "reuse":
            # return existing (no duplicate flag -> API won't 409)
            return {
                "created": False,
                "duplicate": False,
                "message": "Duplicate reused",
                "bill": existing,
            }

        if DUP_POLICY == "suffix":
            # create another bill with a safe suffix
            count = (
                db.query(models.Bill)
                .filter(
                    models.Bill.party_name == data.get("party_name"),
                    models.Bill.bill_no.like(f"{data['bill_no']}%"),
                )
                .count()
            )
            new_no = f"{data['bill_no']}-DUP-{count + 1}"
            data_suffixed = dict(data, bill_no=new_no)
            bill = _create_bill_row(db, data_suffixed, vendor_id)
            return {
                "created": True,
                "duplicate": False,
                "message": f"Duplicate created as {new_no}",
                "bill": bill,
            }

        # strict mode
        return {"duplicate": True, "message": "Duplicate bill exists", "bill": existing}

    # Allow update: patch existing and return it
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
        return {
            "created": False,
            "duplicate": False,
            "message": "Updated existing bill",
            "bill": existing,
        }

    # Fresh create
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

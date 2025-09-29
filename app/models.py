# app/models.py
from __future__ import annotations
from sqlalchemy import (
    Column, Integer, String, Date, ForeignKey, Numeric, Text, DateTime
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

# ---------------- Products ----------------
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    sku = Column(String(64), unique=True, index=True, nullable=True)
    name = Column(String(256), index=True, nullable=False)
    category = Column(String(128), nullable=True)
    price = Column(Numeric(12, 2), nullable=True)
    stock_qty = Column(Numeric(12, 3), nullable=True, default=0)
    reorder_point = Column(Numeric(12, 3), nullable=True, default=0)

    def __repr__(self) -> str:
        return f"<Product {self.id} {self.name}>"

# ---------------- Vendors -----------------
class Vendor(Base):
    __tablename__ = "vendors"
    id = Column(Integer, primary_key=True)
    name = Column(String(256), unique=True, index=True, nullable=False)
    gst_number = Column(String(32), nullable=True)
    address = Column(Text, nullable=True)
    contact = Column(String(64), nullable=True)     # phone
    email = Column(String(256), nullable=True)

    bills = relationship("Bill", back_populates="vendor", cascade="all,delete-orphan")

# ---------------- Bills (legacy OCR) ------
class Bill(Base):
    __tablename__ = "bills"
    id = Column(Integer, primary_key=True)
    bill_no = Column(String(64), index=True, nullable=True)
    bill_date = Column(Date, nullable=True)
    party_name = Column(String(256), nullable=True)
    status = Column(String(32), nullable=False, default="PENDING")
    source = Column(String(32), nullable=True)              # e.g. OCR
    uploaded_doc = Column(String(512), nullable=True)
    total = Column(Numeric(12, 2), nullable=True)

    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    vendor = relationship("Vendor", back_populates="bills")

    lines = relationship("BillLine", back_populates="bill", cascade="all,delete-orphan")

class BillLine(Base):
    __tablename__ = "bill_lines"
    id = Column(Integer, primary_key=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)

    description_raw = Column(Text, nullable=True)
    qty = Column(Numeric(12, 3), nullable=True, default=0)
    unit_price = Column(Numeric(12, 2), nullable=True, default=0)
    line_total = Column(Numeric(12, 2), nullable=True, default=0)
    ocr_confidence = Column(Numeric(4, 3), nullable=True, default=0)

    bill = relationship("Bill", back_populates="lines")
    product = relationship("Product")

# ---------------- Review Queue -----------
class ReviewQueue(Base):
    __tablename__ = "review_queue"
    id = Column(Integer, primary_key=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="OPEN")
    issues = Column(Text, nullable=True)

# ---------------- Stock Ledger -----------
class StockLedger(Base):
    __tablename__ = "stock_ledger"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    qty_change = Column(Numeric(12, 3), nullable=False)
    txn_type = Column(String(32), nullable=False)           # e.g. PURCHASE, ADJUSTMENT
    ref_bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# -------------- Vendor Invoices (new) ----
class Invoice(Base):
    """
    Storage for richer vendor invoices parsed from PDFs (separate from Bill).
    Kept flexible/nullable so it won't break existing data.
    """
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)

    vendor_name = Column(String(256), nullable=True)
    voucher_no = Column(String(64), nullable=True)
    invoice_date = Column(Date, nullable=True)

    bill_to = Column(Text, nullable=True)
    ship_to = Column(Text, nullable=True)

    subtotal = Column(Numeric(12, 2), nullable=True)
    cgst = Column(Numeric(12, 2), nullable=True)
    sgst = Column(Numeric(12, 2), nullable=True)
    igst = Column(Numeric(12, 2), nullable=True)
    other_charges = Column(Numeric(12, 2), nullable=True)
    total = Column(Numeric(12, 2), nullable=True)

    raw_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all,delete-orphan")

class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)

    description = Column(Text, nullable=True)
    hsn = Column(String(16), nullable=True)
    uom = Column(String(16), nullable=True)
    qty = Column(Numeric(12, 3), nullable=True)
    rate = Column(Numeric(12, 2), nullable=True)
    discount_pct = Column(Numeric(5, 2), nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    sku = Column(String(64), nullable=True)

    invoice = relationship("Invoice", back_populates="lines")

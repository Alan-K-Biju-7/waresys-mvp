# app/models.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    String, Integer, Date, DateTime, ForeignKey, Numeric, Text,
    Index, UniqueConstraint, CheckConstraint, Column, Boolean
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# ============================================================
# Vendors
# ============================================================
class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gst_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact: Mapped[str | None] = mapped_column(String(255), nullable=True)

    bills: Mapped[list["Bill"]] = relationship(back_populates="vendor")

    __table_args__ = (
        Index("ix_vendors_gst", "gst_number"),
    )

    def __repr__(self) -> str:
        return f"<Vendor id={self.id} name={self.name!r} gst={self.gst_number!r}>"


# ============================================================
# Products (catalog)
# ============================================================
class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)

    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    stock_qty: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True, default=0)
    reorder_point: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True, default=0)

    def __repr__(self) -> str:
        return f"<Product id={self.id} sku={self.sku!r} name={self.name!r} stock={self.stock_qty}>"


# ============================================================
# Bills (OCR path)
# ============================================================
class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_no: Mapped[str] = mapped_column(String(128), index=True)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)

    party_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING/PROCESSED/CONFIRMED/FAILED
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)  # OCR / MANUAL
    uploaded_doc: Mapped[str | None] = mapped_column(String(512), nullable=True)

    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    vendor: Mapped["Vendor"] = relationship(back_populates="bills")

    lines: Mapped[list["BillLine"]] = relationship(
        back_populates="bill",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # UniqueConstraint("party_name", "bill_no", name="uq_party_billno"),
        Index("ix_bills_date", "bill_date"),
    )

    def __repr__(self) -> str:
        return f"<Bill id={self.id} no={self.bill_no!r} status={self.status}>"


class BillLine(Base):
    __tablename__ = "bill_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), index=True)
    bill: Mapped["Bill"] = relationship(back_populates="lines")

    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    qty: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)

    # Optional GST-ish fields
    hsn: Mapped[str | None] = mapped_column(String(16), nullable=True)
    uom: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        CheckConstraint("qty IS NULL OR qty >= 0", name="ck_bill_lines_qty_nonneg"),
        CheckConstraint("unit_price IS NULL OR unit_price >= 0", name="ck_bill_lines_price_nonneg"),
        CheckConstraint("line_total IS NULL OR line_total >= 0", name="ck_bill_lines_total_nonneg"),
    )

    def __repr__(self) -> str:
        return f"<BillLine id={self.id} bill={self.bill_id} qty={self.qty} hsn={self.hsn} uom={self.uom}>"


# ============================================================
# Review queue
# ============================================================
class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")  # OPEN/RESOLVED
    issues: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ============================================================
# Stock movement ledger
# ============================================================
class StockLedger(Base):
    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    qty_change: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    txn_type: Mapped[str] = mapped_column(String(16))  # IN/OUT/ADJUST
    ref_bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ============================================================
# Parsed Vendor Invoice (new flow)
# ============================================================
class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_name: Mapped[str | None] = mapped_column(String(255))
    voucher_no: Mapped[str | None] = mapped_column(String(128))
    invoice_date: Mapped[date | None] = mapped_column(Date)

    bill_to: Mapped[str | None] = mapped_column(Text)
    ship_to: Mapped[str | None] = mapped_column(Text)

    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    cgst: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sgst: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    igst: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    other_charges: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    raw_text: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Invoice id={self.id} vendor={self.vendor_name!r} total={self.total}>"


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    invoice: Mapped["Invoice"] = relationship(back_populates="lines")

    description: Mapped[str | None] = mapped_column(Text)
    hsn: Mapped[str | None] = mapped_column(String(16))
    uom: Mapped[str | None] = mapped_column(String(16))
    qty: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sku: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint("qty IS NULL OR qty >= 0", name="ck_invoice_lines_qty_nonneg"),
        CheckConstraint("rate IS NULL OR rate >= 0", name="ck_invoice_lines_rate_nonneg"),
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_invoice_lines_amount_nonneg"),
    )

    def __repr__(self) -> str:
        return f"<InvoiceLine id={self.id} invoice={self.invoice_id} qty={self.qty}>"


# ============================================================
# Users (Auth)
# ============================================================
# ============================================================
# Users (Auth)
# ============================================================
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="user")  # admin/user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

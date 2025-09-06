from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Numeric, Date, Text, UniqueConstraint, DateTime, Integer
from sqlalchemy.sql import func
from datetime import date, datetime
from .db import Base

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    uom: Mapped[str] = mapped_column(String, default="pcs", nullable=False)
    reorder_point: Mapped[float] = mapped_column(Numeric(12,2), default=0)

class Bill(Base):
    __tablename__ = "bills"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_type: Mapped[str] = mapped_column(String, nullable=False)  # PURCHASE|SALE
    party_name: Mapped[str | None] = mapped_column(String)
    bill_no: Mapped[str] = mapped_column(String, nullable=False)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)      # OCR|MANUAL
    status: Mapped[str] = mapped_column(String, default="PENDING")   # PENDING|CONFIRMED|VOID
    uploaded_doc: Mapped[str | None] = mapped_column(String)
    __table_args__ = (UniqueConstraint("party_name", "bill_no", name="uq_party_billno"),)

class BillLine(Base):
    __tablename__ = "bill_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    description_raw: Mapped[str | None] = mapped_column(Text)
    qty: Mapped[float] = mapped_column(Numeric(12,3), nullable=False)
    unit_price: Mapped[float | None] = mapped_column(Numeric(12,2))
    line_total: Mapped[float | None] = mapped_column(Numeric(12,2))
    ocr_confidence: Mapped[float | None] = mapped_column(Numeric(4,3), default=0)

class StockLedger(Base):
    __tablename__ = "stock_ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    txn_type: Mapped[str] = mapped_column(String, nullable=False)    # PURCHASE|SALE|ADJUST
    qty_change: Mapped[float] = mapped_column(Numeric(12,3), nullable=False)
    ref_bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)

class ReviewQueue(Base):
    __tablename__ = "review_queue"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"))
    issues: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="OPEN")  # OPEN|RESOLVED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    gst_number: Mapped[str | None] = mapped_column(String, unique=True)
    address: Mapped[str | None] = mapped_column(String)
    contact: Mapped[str | None] = mapped_column(String)

    bills: Mapped[list["Bill"]] = relationship("Bill", back_populates="vendor")


class Bill(Base):
    __tablename__ = "bills"
    id: Mapped[int] = mapped_column(primary_key=True)
    bill_type: Mapped[str] = mapped_column(String, nullable=False)
    party_name: Mapped[str | None] = mapped_column(String)
    bill_no: Mapped[str] = mapped_column(String, nullable=False)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    uploaded_doc: Mapped[str | None] = mapped_column(String)

    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"))
    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="bills")

    __table_args__ = (UniqueConstraint("party_name", "bill_no", name="uq_party_billno"),)
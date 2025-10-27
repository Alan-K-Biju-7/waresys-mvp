from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, Numeric, Text, Index, UniqueConstraint, CheckConstraint, Column, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


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

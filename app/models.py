from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, Numeric, Text, Index, UniqueConstraint, CheckConstraint, Column, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


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

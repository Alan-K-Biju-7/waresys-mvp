from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, Numeric, Text, Index, UniqueConstraint, CheckConstraint, Column, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


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
    hsn: Mapped[str | None] = mapped_column(String(16), nullable=True)
    uom: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        CheckConstraint("qty IS NULL OR qty >= 0", name="ck_bill_lines_qty_nonneg"),
        CheckConstraint("unit_price IS NULL OR unit_price >= 0", name="ck_bill_lines_price_nonneg"),
        CheckConstraint("line_total IS NULL OR line_total >= 0", name="ck_bill_lines_total_nonneg"),
    )

    def __repr__(self) -> str:
        return f"<BillLine id={self.id} bill={self.bill_id} qty={self.qty} hsn={self.hsn} uom={self.uom}>"

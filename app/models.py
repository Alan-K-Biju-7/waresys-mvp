from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, Numeric, Text, Index, UniqueConstraint, CheckConstraint, Column, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_no: Mapped[str] = mapped_column(String(128), index=True)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    party_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uploaded_doc: Mapped[str | None] = mapped_column(String(512), nullable=True)
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    vendor: Mapped["Vendor"] = relationship(back_populates="bills")

    lines: Mapped[list["BillLine"]] = relationship(
        back_populates="bill",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("ix_bills_date", "bill_date"),)

    def __repr__(self) -> str:
        return f"<Bill id={self.id} no={self.bill_no!r} status={self.status}>"

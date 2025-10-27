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

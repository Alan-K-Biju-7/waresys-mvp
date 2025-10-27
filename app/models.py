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

from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, Numeric, Text, Index, UniqueConstraint, CheckConstraint, Column, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


# ============================================================
# Review queue
# ============================================================
class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    issues: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

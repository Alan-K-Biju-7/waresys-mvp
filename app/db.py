from __future__ import annotations

import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.exc import OperationalError

from .config import settings

# Create engine
engine = create_engine(
    settings.DATABASE_URL,  # e.g. postgresql+psycopg://waresys:waresys@db:5432/waresys
    pool_pre_ping=True,
    future=True,
)

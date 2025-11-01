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

# Session factory
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Base class for models
class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Initialize DB connection and create tables if needed."""
    attempts = 0
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except OperationalError:
            attempts += 1
            if attempts >= 20:
                raise
            time.sleep(1)

    # Import models so metadata has tables
    import app.models  # noqa: F401

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

# app/db.py
from __future__ import annotations

import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.exc import OperationalError

from .config import settings

# Engine & Session
engine = create_engine(
    settings.DATABASE_URL,  # e.g. postgresql+psycopg://waresys:waresys@db:5432/waresys
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def init_db() -> None:
    """
    Wait for DB to be ready, import models so metadata is populated,
    then create all tables (idempotent).
    """
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
            time.sleep(1)  # <-- no trailing comma

    # IMPORTANT: populate metadata by importing models
    import app.models  # noqa: F401

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

# api/app/db.py
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.exc import OperationalError
import time
from .config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)

class Base(DeclarativeBase):
    pass

def init_db():
    attempts = 0
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))   # ✅ valid
            break
        except OperationalError:
            attempts += 1
            if attempts >= 20:
                raise
            time.sleep(1)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.exc import OperationalError
import time
from .config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def init_db():
    """
    Create tables with simple retries so Postgres has time to come up.
    """
    from . import models
    attempts = 0
    while True:
        try:
            Base.metadata.create_all(bind=engine)
            break
        except OperationalError:
            attempts += 1
            if attempts >= 20:  # ~20s total
                raise
            time.sleep(1)

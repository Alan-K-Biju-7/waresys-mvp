from __future__ import annotations
import logging, math, os, re
from datetime import date, datetime
from typing import Dict, Any, Optional
from celery import Celery
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app import models, crud

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://redis:6379/0"))
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://redis:6379/0"))
celery_app = Celery("waresys", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------- Prefer the unified pipeline ----------
try:
    from app.ocr_pipeline import process_invoice as pipeline_process  # type: ignore
except Exception:  # pragma: no cover
    pipeline_process = None  # type: ignore

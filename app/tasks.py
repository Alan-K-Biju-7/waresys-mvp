from __future__ import annotations
import logging, math, os, re
from datetime import date, datetime
from typing import Dict, Any, Optional
from celery import Celery
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app import models, crud

# ---------- Celery app ----------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://redis:6379/0"))
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://redis:6379/0"))

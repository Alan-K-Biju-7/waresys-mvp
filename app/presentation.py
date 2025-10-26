
from __future__ import annotations
from datetime import date
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from .db import SessionLocal
from . import crud, models

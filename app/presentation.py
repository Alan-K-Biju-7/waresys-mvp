
from __future__ import annotations
from datetime import date
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from .db import SessionLocal
from . import crud, models
from __future__ import annotations
from datetime import date
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from .db import SessionLocal
from . import crud, models

router = APIRouter(prefix="/api", tags=["presentation"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class CategorySlice(BaseModel):
    category: str
    qty: int

class KPIOut(BaseModel):
    products_total: int
    stock_total_qty: int
    bills_pending: int
    vendors_total: int
    category_breakdown: List[CategorySlice]
class BillRow(BaseModel):
    bill_no: str
    vendor: str
    date: str
    items: int
    total: float
    status: str

class ProductIn(BaseModel):
    sku: Optional[str] = None
    name: str
    category: Optional[str] = None
    stock: int = 0
    price: float = 0.0

class ProductOut(BaseModel):
    sku: Optional[str] = None
    name: str
    category: Optional[str] = None
    stock: int
    price: float

class VendorIn(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None

class VendorOut(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    bills: int = 0

class OCRApproveIn(BaseModel):
    ids: List[str]

class OCRProcessOut(BaseModel):
    vendor: str
    bill_no: str
    date: str
    total: float
    items: int
    inbox_id: str

class OkOut(BaseModel):
    ok: bool

def _coalesce_int(v: Any, default: int = 0) -> int:
    try:
        return int(v or 0)
    except Exception:
        return default

def _coalesce_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v or 0)
    except Exception:
        return default

def _s(val: Any, default: str = "") -> str:
    return str(val) if val is not None else default

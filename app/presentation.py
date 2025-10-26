
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


@router.get("/dashboard/summary", response_model=KPIOut)
def dashboard_summary(db: Session = Depends(get_db)):
    try:
        products_total = db.query(models.Product).count()
    except Exception:
        products_total = 0
    try:
        vendors_total = db.query(models.Vendor).count()
    except Exception:
        vendors_total = 0

    stock_total_qty = 0
    try:
        if hasattr(models.Product, "stock_qty"):
            stock_total_qty = db.query(func.coalesce(func.sum(models.Product.stock_qty), 0)).scalar() or 0
    except Exception:
        stock_total_qty = 0

    bills_pending = 0
    try:
        bills_pending = db.query(models.Bill).filter(models.Bill.status != "PROCESSED").count()
    except Exception:
        bills_pending = 0

    return {
        "products_total": _coalesce_int(products_total),
        "stock_total_qty": _coalesce_int(stock_total_qty),
        "bills_pending": _coalesce_int(bills_pending),
        "vendors_total": _coalesce_int(vendors_total),
        "category_breakdown": [],
    }

@router.get("/bills/recent", response_model=List[BillRow])
def bills_recent(db: Session = Depends(get_db)):
    try:
        Bill = models.Bill
        q = db.query(Bill).order_by(Bill.bill_date.desc()).limit(10).all()
        out: List[BillRow] = []
        for b in q:
            out.append(BillRow(
                bill_no=b.bill_no or str(b.id),
                vendor=b.vendor.name if b.vendor else "—",
                date=b.bill_date.isoformat(),
                items=len(b.lines) if hasattr(b, "lines") else 0,
                total=float(getattr(b, "total", 0)),
                status=b.status or "Pending"
            ))
        return out
    except Exception:
        return []
@router.post("/products")
def create_product(p: ProductIn, db: Session = Depends(get_db)):
    try:
        obj = models.Product(sku=p.sku, name=p.name, category=p.category, stock_qty=p.stock, price=p.price)
        db.add(obj); db.commit(); db.refresh(obj)
        return {"ok": True, "sku": getattr(obj, "sku", p.sku)}
    except Exception as e:
        raise HTTPException(400, f"Create product failed: {e}")
@router.get("/products", response_model=List[ProductOut])
def list_products(q: Optional[str] = None, category: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        items = db.query(models.Product).limit(100).all()
        out: List[ProductOut] = []
        for p in items:
            out.append(ProductOut(
                sku=getattr(p, "sku", None),
                name=p.name,
                category=getattr(p, "category", None),
                stock=_coalesce_int(getattr(p, "stock_qty", 0)),
                price=_coalesce_float(getattr(p, "price", 0.0)),
            ))
        return out
    except Exception:
        return []

@router.get("/vendors", response_model=List[VendorOut])
def list_vendors(db: Session = Depends(get_db)):
    try:
        vs = db.query(models.Vendor).limit(100).all()
        counts = dict(db.query(models.Bill.vendor_id, func.count(models.Bill.id)).group_by(models.Bill.vendor_id).all())
        return [VendorOut(name=v.name, email=v.email, phone=v.phone, bills=int(counts.get(v.id, 0))) for v in vs]
    except Exception:
        return []

@router.post("/ocr/process", response_model=OCRProcessOut)
async def ocr_process(file: UploadFile = File(...)):
    bill_suffix = 110 + (abs(hash(file.filename)) % 900)
    return OCRProcessOut(
        vendor="CERA Distributors",
        bill_no=f"INV-{bill_suffix}",
        date=str(date.today()),
        total=31250.0,
        items=7,
        inbox_id=f"OCR-{abs(hash(file.filename)) % 10000}",
    )

@router.post("/ocr/approve")
def ocr_approve(body: OCRApproveIn):
    return {"ok": True, "approved": len(body.ids)}

@router.post("/reports/publish", response_model=OkOut)
def publish_report():
    return OkOut(ok=True)

# (placeholder - next commit will paste the complete original full code)

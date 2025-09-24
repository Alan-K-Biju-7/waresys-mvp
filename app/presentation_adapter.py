# app/presentation_adapter.py
from __future__ import annotations

from datetime import date
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, select, text

from .db import SessionLocal
from . import crud, models  # adjust paths if needed

router = APIRouter(prefix="/api", tags=["presentation"])


# -----------------------------
# DB session
# -----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------------
# Schemas (responses/inputs)
# -----------------------------
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
    status: str  # "Processed" | "Pending"


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


# -----------------------------
# Helpers
# -----------------------------
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


# -----------------------------
# Endpoints
# -----------------------------
@router.get("/dashboard/summary", response_model=KPIOut)
def dashboard_summary(db: Session = Depends(get_db)):
    """
    Returns KPIs + category donut.
    Robust against minor schema diffs; falls back to demo values if needed.
    """
    # products_total
    try:
        products_total = db.query(models.Product).count()
    except Exception:
        products_total = 0

    # vendors_total
    try:
        vendors_total = db.query(models.Vendor).count()
    except Exception:
        vendors_total = 0

    # stock_total_qty (sum over Product.stock_qty or reasonable aliases)
    stock_total_qty = 0
    try:
        # Prefer Product.stock_qty
        if hasattr(models.Product, "stock_qty"):
            stock_total_qty = db.query(func.coalesce(func.sum(models.Product.stock_qty), 0)).scalar() or 0
        elif hasattr(models.Product, "stock"):
            stock_total_qty = db.query(func.coalesce(func.sum(models.Product.stock), 0)).scalar() or 0
        elif hasattr(models.Product, "quantity"):
            stock_total_qty = db.query(func.coalesce(func.sum(models.Product.quantity), 0)).scalar() or 0
    except Exception:
        stock_total_qty = 0

    # bills_pending
    bills_pending = 0
    try:
        if hasattr(models, "Bill") and hasattr(models.Bill, "status"):
            bills_pending = db.query(models.Bill).filter(models.Bill.status == "Pending").count()
        elif hasattr(models, "Bill") and hasattr(models.Bill, "is_processed"):
            bills_pending = db.query(models.Bill).filter(models.Bill.is_processed.is_(False)).count()
    except Exception:
        bills_pending = 0

    # category_breakdown
    category_breakdown: List[Dict[str, Any]] = []
    try:
        if hasattr(models.Product, "category"):
            # SELECT category, SUM(stock_qty) FROM products GROUP BY category ORDER BY sum DESC LIMIT 6
            qty_col = (
                models.Product.stock_qty
                if hasattr(models.Product, "stock_qty")
                else (
                    models.Product.stock
                    if hasattr(models.Product, "stock")
                    else (
                        models.Product.quantity
                        if hasattr(models.Product, "quantity")
                        else None
                    )
                )
            )
            if qty_col is not None:
                rows = (
                    db.query(
                        func.coalesce(models.Product.category, "Uncategorized").label("c"),
                        func.coalesce(func.sum(qty_col), 0).label("qty"),
                    )
                    .group_by(func.coalesce(models.Product.category, "Uncategorized"))
                    .order_by(func.sum(qty_col).desc())
                    .limit(6)
                    .all()
                )
                category_breakdown = [{"category": _s(r.c, "Uncategorized"), "qty": _coalesce_int(r.qty)} for r in rows]
    except Exception:
        category_breakdown = []

    # Fallback demo dataset if empty (keeps UI pretty for the presentation)
    if not category_breakdown:
        category_breakdown = [
            {"category": "Tiles", "qty": 26000},
            {"category": "Sanitaryware", "qty": 14000},
            {"category": "Cement", "qty": 9000},
            {"category": "Steel", "qty": 8000},
            {"category": "Adhesives", "qty": 4990},
        ]

    return {
        "products_total": _coalesce_int(products_total),
        "stock_total_qty": _coalesce_int(stock_total_qty),
        "bills_pending": _coalesce_int(bills_pending),
        "vendors_total": _coalesce_int(vendors_total),
        "category_breakdown": category_breakdown,
    }


@router.get("/bills/recent", response_model=List[BillRow])
def bills_recent(db: Session = Depends(get_db)):
    """
    Returns recent bills. Tries (in order):
    1) Join Bill -> Vendor (if vendor relation/id exists)
    2) Use Bill.vendor_name field
    3) Fallback demo data
    """
    try:
        if hasattr(models, "Bill"):
            Bill = models.Bill
            # date column guess
            date_col = None
            for cand in ("date", "bill_date", "created_at"):
                if hasattr(Bill, cand):
                    date_col = getattr(Bill, cand)
                    break

            # total column guess
            total_col = None
            for cand in ("total", "total_amount", "grand_total", "amount"):
                if hasattr(Bill, cand):
                    total_col = getattr(Bill, cand)
                    break

            # items count guess (if a BillLine model exists)
            items_count_by_bill: Dict[Any, int] = {}
            try:
                if hasattr(models, "BillLine") and hasattr(models.BillLine, "bill_id"):
                    q = (
                        db.query(models.BillLine.bill_id, func.count(models.BillLine.id))
                        .group_by(models.BillLine.bill_id)
                        .all()
                    )
                    items_count_by_bill = {bid: int(cnt) for (bid, cnt) in q}
            except Exception:
                items_count_by_bill = {}

            # case 1: vendor relation (vendor_id + Vendor model)
            if hasattr(Bill, "vendor_id") and hasattr(models, "Vendor"):
                Vendor = models.Vendor
                q = db.query(Bill, Vendor).join(Vendor, Bill.vendor_id == Vendor.id)
                if date_col is not None:
                    q = q.order_by(date_col.desc())
                rows = q.limit(10).all()

                out: List[BillRow] = []
                for b, v in rows:
                    bill_no = _s(getattr(b, "bill_no", None)) or _s(getattr(b, "number", None)) or _s(getattr(b, "id", None))
                    vendor_name = _s(getattr(v, "name", None)) or "—"
                    dt = getattr(b, "date", None) or getattr(b, "bill_date", None) or getattr(b, "created_at", None)
                    dt_str = _s((dt.isoformat()[:10] if hasattr(dt, "isoformat") else dt)) or _s(getattr(b, "date_str", None)) or ""
                    items = items_count_by_bill.get(getattr(b, "id", None), 0)
                    total_val = _coalesce_float(getattr(b, "total", None) if total_col is None else total_col.__get__(b, Bill))
                    status = _s(getattr(b, "status", None)) or ("Processed" if _coalesce_float(total_val) > 0 else "Pending")
                    out.append(BillRow(bill_no=bill_no, vendor=vendor_name, date=dt_str, items=items, total=total_val, status=status))
                if out:
                    return out

            # case 2: vendor_name column on Bill
            if hasattr(Bill, "vendor_name"):
                q = db.query(Bill)
                if date_col is not None:
                    q = q.order_by(date_col.desc())
                rows = q.limit(10).all()

                out2: List[BillRow] = []
                for b in rows:
                    bill_no = _s(getattr(b, "bill_no", None)) or _s(getattr(b, "number", None)) or _s(getattr(b, "id", None))
                    vendor_name = _s(getattr(b, "vendor_name", None)) or "—"
                    dt = getattr(b, "date", None) or getattr(b, "bill_date", None) or getattr(b, "created_at", None)
                    dt_str = _s((dt.isoformat()[:10] if hasattr(dt, "isoformat") else dt)) or _s(getattr(b, "date_str", None)) or ""
                    items = items_count_by_bill.get(getattr(b, "id", None), 0)
                    total_val = _coalesce_float(getattr(b, "total", None) if total_col is None else total_col.__get__(b, Bill))
                    status = _s(getattr(b, "status", None)) or ("Processed" if _coalesce_float(total_val) > 0 else "Pending")
                    out2.append(BillRow(bill_no=bill_no, vendor=vendor_name, date=dt_str, items=items, total=total_val, status=status))
                if out2:
                    return out2

    except Exception:
        pass

    # Fallback demo
    return [
        {"bill_no": "INV-1001", "vendor": "Alpha Traders", "date": "2025-09-20", "items": 12, "total": 48700, "status": "Processed"},
        {"bill_no": "INV-1002", "vendor": "Delta Ceramics", "date": "2025-09-21", "items": 8, "total": 23950, "status": "Pending"},
        {"bill_no": "INV-1003", "vendor": "RAK Distributors", "date": "2025-09-21", "items": 5, "total": 15320, "status": "Pending"},
    ]


@router.get("/products", response_model=List[ProductOut])
def list_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Returns product list. Uses your CRUD search if available, else a direct query.
    Attempts to read common column names for stock & price.
    """
    try:
        if q and hasattr(crud, "search_products_by_name"):
            items = crud.search_products_by_name(db, q=q, limit=100)
        else:
            items = db.query(models.Product).limit(100).all()
        # Optional filter by category (client sends "All Categories" when not filtering)
        if category and category != "All Categories":
            items = [p for p in items if _s(getattr(p, "category", None)) == category]

        out: List[ProductOut] = []
        for p in items:
            stock_val = None
            for cand in ("stock_qty", "stock", "quantity", "qty"):
                if hasattr(p, cand):
                    stock_val = getattr(p, cand)
                    break
            price_val = None
            for cand in ("price", "unit_price", "sale_price"):
                if hasattr(p, cand):
                    price_val = getattr(p, cand)
                    break
            out.append(
                ProductOut(
                    sku=_s(getattr(p, "sku", None)) or None,
                    name=_s(getattr(p, "name", None)),
                    category=_s(getattr(p, "category", None)) or None,
                    stock=_coalesce_int(stock_val),
                    price=_coalesce_float(price_val),
                )
            )
        if out:
            return out
    except Exception:
        pass

    # Fallback demo
    return [
        ProductOut(sku="AUTO-1A2B3C", name="Tiles 600x600", category="Tiles", stock=120, price=245.00),
        ProductOut(sku="AUTO-4D5E6F", name="Sanitaryware Basin", category="Sanitaryware", stock=80, price=1200.00),
    ]


@router.post("/products", response_model=Dict[str, Any])
def create_product(p: ProductIn, db: Session = Depends(get_db)):
    """
    Creates a product using your CRUD create (if present) or a direct model add.
    """
    try:
        if hasattr(crud, "create_product"):
            obj = crud.create_product(
                db,
                sku=p.sku,
                name=p.name,
                category=p.category,
                stock_qty=p.stock,
                price=p.price,
            )
            return {"ok": True, "sku": getattr(obj, "sku", p.sku)}
        else:
            obj = models.Product(
                sku=p.sku,
                name=p.name,
                category=p.category,
                stock_qty=p.stock if hasattr(models.Product, "stock_qty") else None,
                price=p.price if hasattr(models.Product, "price") else None,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
            return {"ok": True, "sku": getattr(obj, "sku", p.sku)}
    except Exception as e:
        raise HTTPException(400, f"Create product failed: {e}")


@router.get("/vendors", response_model=List[VendorOut])
def list_vendors(db: Session = Depends(get_db)):
    """
    Returns vendor list with a best-effort bills count if Bill model exists.
    """
    try:
        vs = db.query(models.Vendor).limit(100).all()
        counts: Dict[Any, int] = {}
        try:
            if hasattr(models, "Bill") and hasattr(models.Bill, "vendor_id") and hasattr(models.Bill, "id"):
                q = db.query(models.Bill.vendor_id, func.count(models.Bill.id)).group_by(models.Bill.vendor_id).all()
                counts = {vid: int(cnt) for (vid, cnt) in q}
        except Exception:
            counts = {}

        out: List[VendorOut] = []
        for v in vs:
            vid = getattr(v, "id", None)
            out.append(
                VendorOut(
                    name=_s(getattr(v, "name", None)),
                    email=_s(getattr(v, "email", None)) or None,
                    phone=_s(getattr(v, "phone", None)) or None,
                    bills=int(counts.get(vid, 0)),
                )
            )
        if out:
            return out
    except Exception:
        pass

    # Fallback demo
    return [
        VendorOut(name="Alpha Traders", email="alpha@ex.com", phone="+91 98765 43210", bills=132),
        VendorOut(name="Delta Ceramics", email="delta@ex.com", phone="+91 91234 56789", bills=88),
    ]


@router.post("/vendors", response_model=Dict[str, Any])
def create_vendor(v: VendorIn, db: Session = Depends(get_db)):
    """
    Creates a vendor with minimal fields.
    """
    try:
        obj = models.Vendor(name=v.name, email=v.email, phone=v.phone)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return {"ok": True, "id": getattr(obj, "id", None)}
    except Exception as e:
        raise HTTPException(400, f"Create vendor failed: {e}")


@router.post("/ocr/process", response_model=OCRProcessOut)
async def ocr_process(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Hook this to your real OCR pipeline (Celery task or inline).
    For the presentation, returns a consistent mock preview shape.
    """
    # TODO: integrate with your real OCR -> parse -> temp DB/inbox if needed
    bill_suffix = 110 + (abs(hash(file.filename)) % 900)
    inbox_suffix = abs(hash(file.filename)) % 10_000
    return OCRProcessOut(
        vendor="CERA Distributors",
        bill_no=f"INV-{bill_suffix}",
        date=str(date.today()),
        total=31250.0,
        items=7,
        inbox_id=f"OCR-{inbox_suffix}",
    )


@router.post("/ocr/approve", response_model=Dict[str, Any])
def ocr_approve(body: OCRApproveIn, db: Session = Depends(get_db)):
    """
    Approves OCR inbox items.
    Wire this to your confirm_bill() or bill creation logic as available.
    """
    # Example:
    # from .stock import confirm_bill
    # for iid in body.ids:
    #     confirm_bill(db, inbox_id=iid)
    return {"ok": True, "approved": len(body.ids), "bills_pending_delta": -len(body.ids)}


@router.post("/reports/publish", response_model=OkOut)
def publish_report():
    """
    Trivial publish endpoint for the UI.
    """
    return OkOut(ok=True)

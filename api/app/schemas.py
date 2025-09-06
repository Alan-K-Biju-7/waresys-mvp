from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime,date

class ProductIn(BaseModel):
    sku: str
    name: str
    category_id: Optional[int] = None
    uom: str = "pcs"
    reorder_point: float = 0

class ProductOut(ProductIn):
    id: int
    class Config: from_attributes = True

class ParsedLine(BaseModel):
    description_raw: str
    qty: float
    unit_price: float | None = None
    line_total: float | None = None
    candidate_product_ids: list[int] = Field(default_factory=list)
    match_score: float = 0.0
    ocr_confidence: float = 0.0
    resolved_product_id: int | None = None

class OCRResult(BaseModel):
    bill_id: int
    party_name: str | None = None
    bill_no: str | None = None
    bill_date: str | None = None
    due_date: str | None = None        # NEW
    po_number: str | None = None       # NEW
    total: float | None = None         # NEW
    lines: List[ParsedLine]
    needs_review: bool
    message: str


class ConfirmRequest(BaseModel):
    bill_type: str

class BillCreate(BaseModel):
    bill_type: str
    party_name: Optional[str] = None
    bill_no: str
    bill_date: Optional[str] = None   # <-- more flexible
    source: str
    status: str
    uploaded_doc: str


class BillOut(BaseModel):
    id: int
    bill_type: str
    party_name: Optional[str] = None
    bill_no: str
    bill_date: date
    source: str
    status: str
    uploaded_doc: str

    class Config:
        from_attributes = True   # <-- fix for Pydantic v2

class ReviewOut(BaseModel):
    id: int
    bill_id: int
    status: str
    issues: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ReviewResolve(BaseModel):
    notes: Optional[str] = None

class VendorBase(BaseModel):
    name: str
    gst_number: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None

class VendorCreate(VendorBase):
    pass

class VendorOut(VendorBase):
    id: int
    class Config:
        from_attributes = True


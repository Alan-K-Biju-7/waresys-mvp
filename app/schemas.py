from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List, Any
from pydantic import BaseModel, Field, StringConstraints
from typing_extensions import Annotated

# ------ Products ------
class ProductIn(BaseModel):
    sku: str
    name: str
    category_id: Optional[int] = None
    uom: str = "pcs"
    reorder_point: float = 0

class ProductOut(ProductIn):
    id: int
    model_config = {"from_attributes": True}

# ------ OCR / Parsing ------
class ParsedLine(BaseModel):
    description_raw: str
    qty: float
    unit_price: float | None = None
    line_total: float | None = None
    candidate_product_ids: list[int] = Field(default_factory=list)
    match_score: float = 0.0
    ocr_confidence: float = 0.0
    resolved_product_id: int | None = None
    uom: str | None = None
    hsn: str | None = None

class OCRResult(BaseModel):
    bill_id: int
    party_name: str | None = None
    bill_no: str | None = None
    bill_date: str | None = None
    due_date: str | None = None
    po_number: str | None = None
    total: float | None = None
    lines: List[ParsedLine]
    needs_review: bool
    message: str

class ConfirmRequest(BaseModel):
    bill_type: str

# ------ Bills (create) ------
class BillCreate(BaseModel):
    bill_type: str
    party_name: Optional[str] = None
    bill_no: str
    bill_date: Optional[str] = None
    source: str
    status: str
    uploaded_doc: str

# ------ Review Queue ------
class ReviewOut(BaseModel):
    id: int
    bill_id: int
    status: str
    issues: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}

class ReviewResolve(BaseModel):
    notes: Optional[str] = None

# ------ Vendors ------
class VendorBase(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    gst_number: str | None = None
    address: str | None = None
    contact: str | None = None

class VendorCreate(VendorBase):
    pass

class VendorOut(VendorBase):
    id: int
    model_config = {"from_attributes": True}

# ------ Bill Lines ------
class BillLineOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    description_raw: Optional[str] = None
    qty: float
    unit_price: Optional[float] = None
    line_total: Optional[float] = None
    ocr_confidence: float = 0.0
    uom: Optional[str] = None
    hsn: Optional[str] = None
    model_config = {"from_attributes": True}

# ------ Bill (rich) ------
class BillOut(BaseModel):
    id: int
    bill_no: str
    bill_date: date
    party_name: Optional[str] = None
    status: str
    source: str
    uploaded_doc: Optional[str] = None
    vendor: Optional[VendorOut] = None
    lines: List[BillLineOut] = Field(default_factory=list)
    needs_review: bool = False
    model_config = {"from_attributes": True}

# ------ Auth / Users ------
Password72 = Annotated[str, StringConstraints(min_length=1, max_length=72)]

class UserRegister(BaseModel):
    email: str
    password: Password72
    role: str = "user"

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

from pydantic import BaseModel, Field
from typing import Optional, List

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
    lines: List[ParsedLine]
    needs_review: bool
    message: str

class ConfirmRequest(BaseModel):
    bill_type: str

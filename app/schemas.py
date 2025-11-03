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

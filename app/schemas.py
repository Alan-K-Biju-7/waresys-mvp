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

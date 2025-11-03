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

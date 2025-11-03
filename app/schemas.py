class ReviewOut(BaseModel):
    id: int
    bill_id: int
    status: str
    issues: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}

class BillCreate(BaseModel):
    bill_type: str
    party_name: Optional[str] = None
    bill_no: str
    bill_date: Optional[str] = None
    source: str
    status: str
    uploaded_doc: str

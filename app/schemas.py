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
    total: Optional[float] = None
    model_config = {"from_attributes": True}


Password72 = Annotated[str, StringConstraints(min_length=1, max_length=72)]

class UserRegister(BaseModel):
    email: str
    password: Password72
    role: str = "user"

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

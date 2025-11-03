class VendorBase(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    gst_number: str | None = None
    address: str | None = None
    contact: str | None = None

class VendorCreate(VendorBase):
    pass

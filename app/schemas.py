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

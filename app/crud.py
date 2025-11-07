import os
import re
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import models, schemas

# ============================================================
# Duplicate policy for Bills
# ============================================================
DUP_POLICY = os.getenv("DUP_POLICY", "reuse").strip().lower()

# ============================================================
# Vendor classification tokens (positive/negative)
# ============================================================
_POS_VENDOR_TOKENS = re.compile(
    r"(A2Z|BUILDWARES?|TILE|TILES|SANIT|HARDWARE|CERAM|PVT|LTD|LLP|CO\.?|COMPANY|ENTERPRISES?|AGENC(?:Y|IES)|CERAMIC|BATH|SANITARY)",
    re.I,
)

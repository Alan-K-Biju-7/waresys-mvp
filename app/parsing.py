
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from .vendor_detection import detect_vendor_from_lines

logger = logging.getLogger(__name__)


def normalize_text(ocr_text: str) -> str:
    """
    Normalize raw OCR text by:
    - Converting carriage returns to newlines
    - Collapsing multiple spaces/tabs
    - Reducing extra blank lines
    - Stripping leading/trailing whitespace
    """
    text = ocr_text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()

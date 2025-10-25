
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
def _clean_num(s: str) -> str:
    """
    Clean numeric OCR strings by:
    - Replacing letter 'O' or 'o' with zero
    - Removing commas and currency symbols
    - Stripping whitespace
    """
    s = s.replace("O", "0").replace("o", "0")
    s = s.replace(",", "")
    s = s.replace("₹", "").replace("$", "")
    return s.strip()


def parse_header(ocr_text: str) -> Dict[str, Optional[str]]:
    """
    Very light header parser to support miscellaneous/legacy bills.
    Extracts fields: bill_no, bill_date, total, and party_name.
    """
    text = normalize_text(ocr_text)
    patterns = {
        "bill_no": r"(?:Invoice\s*No\.?|Bill\s*No\.?)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        "bill_date": r"(?:Date)\s*[:\-]?\s*(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})",
        "total": r"(?:Grand\s*Total|Total\s*Amount|Total)\s*[:\-]?\s*([0-9,]+(?:\.\d{1,2})?)",
        "party_name": r"(?:To|Party|Vendor|Customer)\s*[:\-]?\s*([A-Za-z0-9 &.,\-]+)",
    }
    out: Dict[str, Optional[str]] = {}
    for k, p in patterns.items():
        m = re.search(p, text, re.IGNORECASE)
        if not m:
            out[k] = None
        elif k == "total":
            out[k] = _clean_num(m.group(1))
        else:
            out[k] = m.group(1).strip()
    return out

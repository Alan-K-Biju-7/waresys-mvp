import re
from typing import List, Dict, Any, Optional

# ---------------------- Regex Patterns ----------------------
FIELD_PATTERNS = {
    "bill_no": [
        r"(?:Invoice\s*No|Invoice|Inv|Bill|No)\s*[:\-#]?\s*([A-Za-z0-9\-_/]+)"
    ],
    "bill_date": [
        r"(?:Invoice\s*Date|Bill\s*Date|Date)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
    ],
    "due_date": [
        r"(?:Due\s*Date|Payment\s*Due)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
    ],
    "total": [
        r"(?:Grand\s*Total|Total\s*Amount|Amount\s*Payable)\s*[:\-]?\s*([\d,]+\.\d{2})"
    ],
    "po_number": [
        r"(?:PO\s*No|Purchase\s*Order)\s*[:\-]?\s*([A-Za-z0-9\-_/]+)"
    ]
}


def parse_kv_fields_from_zone(text: str) -> Dict[str, Optional[str]]:
    """Try to extract key-value fields using regex aliases from a text zone."""
    results: Dict[str, Optional[str]] = {}
    for field, patterns in FIELD_PATTERNS.items():
        results[field] = None
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                results[field] = m.group(1).strip()
                break
    return results


def parse_line_items_from_tokens(tokens: List[str]) -> List[Dict[str, Any]]:
    """Parse line items by detecting qty, unit price, total, with confidence scoring."""
    joined = " ".join(tokens)
    rows = re.split(r"\n|  {2,}|\t|\r", joined)
    out: List[Dict[str, Any]] = []

    for r in rows:
        numbers = re.findall(r"(\d+(?:\.\d{1,2})?)", r)
        if not numbers:
            continue

        desc = re.sub(r"\d+(?:\.\d{1,2})?", "", r).strip()
        qty = float(numbers[0]) if len(numbers) >= 1 else None
        unit_price = float(numbers[1]) if len(numbers) >= 2 else None
        line_total = float(numbers[2]) if len(numbers) >= 3 else None

        # Confidence scoring
        conf = 0.5
        if qty and unit_price and line_total:
            if abs((qty * unit_price) - line_total) < 1:
                conf = 0.95
            else:
                conf = 0.7
        elif qty and unit_price:
            conf = 0.8

        out.append({
            "description_raw": desc[:200] or r[:200],
            "qty": qty,
            "unit_price": unit_price,
            "line_total": line_total,
            "ocr_confidence": conf
        })

    return out[:50]

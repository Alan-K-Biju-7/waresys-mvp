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
    """Extract key-value fields (bill no, date, total, etc.) using regex."""
    results: Dict[str, Optional[str]] = {}
    for field, patterns in FIELD_PATTERNS.items():
        results[field] = None
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                results[field] = m.group(1).strip()
                break
    return results

def parse_line_items_from_tokens(lines: List[str]) -> List[Dict[str, Any]]:
    """
    Parse invoice line items from OCR text lines.
    """
    out: List[Dict[str, Any]] = []
    in_table = False

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue

        # Detect start of table
        if not in_table and "Qty" in raw and "Unit" in raw:
            in_table = True
            continue

        if in_table:
            # Flexible parser: qty first, unit_price + total last
            parts = raw.split()
            if len(parts) < 5:
                continue

            try:
                qty = float(parts[0])
                sku = parts[1].upper()
                unit_price = float(parts[-2])
                line_total = float(parts[-1])
                desc = " ".join(parts[2:-2])

                conf = 0.95 if abs((qty * unit_price) - line_total) < 1 else 0.7

                out.append({
                    "sku": sku,
                    "description_raw": desc,
                    "qty": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "ocr_confidence": conf
                })
            except Exception:
                continue

    return out

import re
from typing import List, Dict

DATE_RX = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
INV_RX = re.compile(r"\b(INV|Invoice|Bill)\s*[:#]?\s*([A-Za-z0-9\-_/]+)\b", re.I)

def parse_kv_fields(tokens: List[str]) -> Dict[str, str | None]:
    joined = " ".join(tokens)
    date = (DATE_RX.search(joined).group(1) if DATE_RX.search(joined) else None)
    bill_no = (INV_RX.search(joined).group(2) if INV_RX.search(joined) else None)
    party = joined.split("Invoice")[0].strip()[:64] if "Invoice" in joined else None
    return {"bill_no": bill_no, "bill_date": date, "party_name": party}

def parse_line_items_from_tokens(tokens: List[str]) -> List[Dict]:
    joined = " ".join(tokens)
    rows = re.split(r"\n|  {2,}|\t|\r", joined)
    out = []
    for r in rows:
        q = re.search(r"(\d+(?:\.\d{1,3})?)\s*(pcs|kg|ltr|ml|nos)?", r, re.I)
        p = re.search(r"(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})|\d+\.\d{1,2})\s*(INR|Rs|SAR|\$)?$", r)
        if q:
            desc = r
            qty = float(q.group(1))
            unit = (q.group(2) or "").lower()
            price = float(p.group(1).replace(",", "")) if p else None
            out.append({"description_raw": desc[:200], "qty": qty, "unit": unit, "unit_price": price, "line_total": None})
    return out[:50]

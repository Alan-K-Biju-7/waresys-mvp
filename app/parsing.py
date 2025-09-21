import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

def normalize_text(ocr_text: str) -> str:
    # collapse whitespace but keep newlines for ^$ regex
    text = ocr_text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()

def _clean_num(s: str) -> str:
    # Fix common OCR mistakes and remove thousands separators
    s = s.replace("O", "0").replace("o", "0")
    s = s.replace(",", "")
    s = s.replace("₹", "").replace("$", "")
    return s.strip()

def parse_header(ocr_text: str) -> Dict[str, str]:
    text = normalize_text(ocr_text)
    patterns = {
        "bill_no": r"(?:Invoice\s*No\.?|Bill\s*No\.?)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        "bill_date": r"(?:Date)\s*[:\-]?\s*(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})",
        "total": r"(?:Grand\s*Total|Total\s*Amount|Total)\s*[:\-]?\s*([0-9,]+(?:\.\d{1,2})?)",
        "party_name": r"(?:To|Party|Vendor|Customer)\s*[:\-]?\s*([A-Za-z0-9 &.,\-]+)"
    }
    out = {}
    for k, p in patterns.items():
        m = re.search(p, text, re.IGNORECASE)
        out[k] = _clean_num(m.group(1)) if k == "total" and m else (m.group(1).strip() if m else None)
    return out

def parse_lines(ocr_text: str) -> List[Dict]:
    """
    Extract line items in flexible formats, e.g.:
      12  Cement OPC 50kg bag         380.00  4560.00
      8   Galvanized Bracket L-50     120     960
      5   Screws M6x30                ₹85     ₹425
    Fallback: qty at start, last two tokens are prices.
    """
    text = normalize_text(ocr_text)

    # Common numeric pattern allowing thousands and optional decimals
    MONEY = r"[₹$]?\s*[0-9][0-9,]*(?:\.\d{1,2})?"
    QTY = r"\d+"

    patterns = [
        # qty desc unit_price line_total
        re.compile(rf"^\s*({QTY})\s+(.+?)\s+({MONEY})\s+({MONEY})\s*$", re.MULTILINE),
        # qty desc line_total (no explicit unit price) → infer unit_price = total/qty
        re.compile(rf"^\s*({QTY})\s+(.+?)\s+({MONEY})\s*$", re.MULTILINE),
    ]

    parsed: List[Dict] = []

    # Try regex patterns first
    for pat in patterns:
        matches = pat.findall(text)
        if matches:
            for i, m in enumerate(matches, start=1):
                if len(m) == 4:
                    qty_s, desc, up_s, lt_s = m
                    qty = int(_clean_num(qty_s))
                    unit_price = float(_clean_num(up_s))
                    line_total = float(_clean_num(lt_s))
                else:
                    qty_s, desc, lt_s = m
                    qty = int(_clean_num(qty_s))
                    line_total = float(_clean_num(lt_s))
                    unit_price = round(line_total / max(qty, 1), 2)

                parsed.append({
                    "id": len(parsed) + 1,
                    "product_id": None,
                    "description_raw": desc.strip(),
                    "qty": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "ocr_confidence": 0.95
                })
            return parsed  # stop at first successful pattern

    # Fallback: heuristic column split
    fallback = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # must start with qty
        m = re.match(rf"^\s*({QTY})\s+(.+)$", line)
        if not m:
            continue
        qty = int(_clean_num(m.group(1)))
        rest = m.group(2)

        # take last two numeric tokens as prices if present, else skip
        tokens = rest.split()
        nums = [t for t in tokens if re.fullmatch(MONEY, t)]
        if len(nums) >= 2:
            lt_s = _clean_num(nums[-1])
            up_s = _clean_num(nums[-2])
            # description is everything before the last two nums
            try:
                cut = rest.rfind(nums[-2])
                desc = rest[:cut].strip()
                unit_price = float(up_s)
                line_total = float(_clean_num(lt_s))
                fallback.append({
                    "id": len(parsed) + len(fallback) + 1,
                    "product_id": None,
                    "description_raw": desc,
                    "qty": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "ocr_confidence": 0.9
                })
            except Exception:
                continue

    if fallback:
        logger.info(f"Fallback parser captured {len(fallback)} lines")
        return fallback

    return []  # nothing matched

def deduplicate_lines(lines: List[Dict]) -> List[Dict]:
    """Remove duplicates by description + qty + prices."""
    seen = set()
    unique = []
    for line in lines:
        key = (line["description_raw"].lower(), line["qty"], round(line["unit_price"], 2), round(line["line_total"], 2))
        if key not in seen:
            seen.add(key)
            unique.append(line)
    return unique

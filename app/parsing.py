# app/parsing.py
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from .vendor_detection import detect_vendor_from_lines

logger = logging.getLogger(__name__)

# ==============================
# Shared helpers (legacy bill)
# ==============================

def normalize_text(ocr_text: str) -> str:
    text = ocr_text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()

def _clean_num(s: str) -> str:
    s = s.replace("O", "0").replace("o", "0")
    s = s.replace(",", "")
    s = s.replace("₹", "").replace("$", "")
    return s.strip()

def parse_header(ocr_text: str) -> Dict[str, Optional[str]]:
    """
    Very light header parser to support miscellaneous/legacy bills.
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

# ---- sanity guards to avoid DB numeric overflow from bad OCR ----
_QTY_MAX = 1_000_000        # qty beyond this is almost surely OCR noise
_PRICE_MAX = 10_000_000     # likewise for unit price
_LINE_TOTAL_MAX = 50_000_000

def _is_sane(qty: float, unit_price: float, line_total: float) -> bool:
    if qty < 0 or unit_price < 0 or line_total < 0:
        return False
    if qty > _QTY_MAX or unit_price > _PRICE_MAX or line_total > _LINE_TOTAL_MAX:
        return False
    # also reject if the implied price is absurd
    if qty > 0 and (line_total / max(qty, 1)) > _PRICE_MAX:
        return False
    return True

def parse_lines(ocr_text: str) -> List[Dict]:
    """
    Legacy-ish line parser:
    - Handles: QTY DESC UNIT_PRICE LINE_TOTAL   or
               QTY DESC LINE_TOTAL  (unit_price inferred)
    - Applies sanity checks to avoid inserting garbage rows.
    """
    text = normalize_text(ocr_text)
    MONEY = r"[₹$]?\s*[0-9][0-9,]*(?:\.\d{1,2})?"
    QTY = r"\d+"

    patterns = [
        re.compile(rf"^\s*({QTY})\s+(.+?)\s+({MONEY})\s+({MONEY})\s*$", re.MULTILINE),
        re.compile(rf"^\s*({QTY})\s+(.+?)\s+({MONEY})\s*$", re.MULTILINE),
    ]

    parsed: List[Dict] = []
    for pat in patterns:
        matches = pat.findall(text)
        if matches:
            for m in matches:
                if len(m) == 4:
                    qty_s, desc, up_s, lt_s = m
                    qty = float(_clean_num(qty_s) or "0")
                    unit_price = float(_clean_num(up_s) or "0")
                    line_total = float(_clean_num(lt_s) or "0")
                else:
                    qty_s, desc, lt_s = m
                    qty = float(_clean_num(qty_s) or "0")
                    line_total = float(_clean_num(lt_s) or "0")
                    unit_price = round(line_total / max(qty, 1.0), 2)

                if not _is_sane(qty, unit_price, line_total):
                    logger.info("[parse_lines] skipping insane row: %s / %s / %s :: %s",
                                qty, unit_price, line_total, desc[:80])
                    continue

                parsed.append({
                    "id": len(parsed) + 1,
                    "product_id": None,
                    "description_raw": desc.strip(),
                    "qty": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "ocr_confidence": 0.95,
                })
            break  # stop after first matching pattern

    return parsed

def deduplicate_lines(lines: List[Dict]) -> List[Dict]:
    seen = set()
    unique = []
    for line in lines:
        key = (
            (line.get("description_raw") or "").lower(),
            round(float(line.get("qty") or 0), 3),
            round(float(line.get("unit_price") or 0), 2),
            round(float(line.get("line_total") or 0), 2),
        )
        if key not in seen:
            seen.add(key)
            unique.append(line)
    return unique

# =========================================
# Vendor-style invoice parsing (GST aware)
# =========================================

# GSTIN format: 2 digits + 5 letters + 4 digits + 1 letter + 1 alnum + 'Z' + 1 alnum
GSTIN_RE = r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b"
INR_CAPTURE = r"(?:₹\s*)?([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{1,2})|[0-9]+(?:\.\d{1,2})?)"

def _to_decimal(x: Optional[str]) -> Decimal:
    if not x:
        return Decimal("0")
    return Decimal(x.replace(",", ""))

def _find_email(text: str) -> Optional[str]:
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return m.group(0) if m else None

def _find_phone(text: str) -> Optional[str]:
    # loose phone capture; then compress digits (keep + if present)
    m = re.search(r"(\+?\d[\d \-]{8,}\d)", text)
    if not m:
        return None
    raw = m.group(1)
    digits = re.sub(r"[^\d+]", "", raw)
    return digits

def _top_nonempty_lines(text: str, n: int = 40) -> List[str]:
    return [l.strip() for l in text.splitlines() if l.strip()][:n]

def _guess_vendor_name(text: str) -> Optional[str]:
    """
    Heuristics:
    - Look at top lines; prefer those with business-y tokens or ALLCAPS words.
    - Fallback to line immediately above GSTIN, if found.
    """
    lines = _top_nonempty_lines(text, 50)
    tokens = re.compile(r"(BUILDWARE|TILE|SANIT|TRAD(?:E|ERS)?|HARDWARE|PVT|LTD|LLP|&|M(?:\s*&\s*)?S\.?)", re.I)

    for l in lines[:10]:
        if tokens.search(l) and not re.search(r"tax invoice|invoice|voucher|bill", l, re.I):
            return l.strip()

    # try a line immediately preceding GSTIN
    for idx, l in enumerate(lines):
        if re.search(GSTIN_RE, l):
            if idx > 0:
                return lines[idx - 1]
            break

    # last resort: first line that isn't "Tax Invoice" etc.
    for l in lines[:6]:
        if not re.search(r"tax\s*invoice|invoice|voucher", l, re.I):
            return l
    return None

def _extract_vendor_block(text: str) -> Dict[str, Optional[str]]:
    """
    Pull vendor {name, gst_number, address, contact, email} from the header.
    """
    header = "\n".join(_top_nonempty_lines(text, 100))
    name = _guess_vendor_name(header)
    gst = None
    addr = None
    email = _find_email(header)
    phone = _find_phone(header)

    m_gst = re.search(GSTIN_RE, header)
    if m_gst:
        gst = m_gst.group(0)

    # Address: take up to ~4 lines following the detected name (or top area) until clear break
    addr_lines: List[str] = []
    if name:
        lines = header.splitlines()
        try:
            start = next(i for i, l in enumerate(lines) if name in l)
        except StopIteration:
            start = 0
        for l in lines[start + 1 : start + 6]:
            if re.search(GSTIN_RE, l, re.I):
                continue
            if re.search(r"(phone|mob|email|gst|pan|cin|uin)[:\s]", l, re.I):
                continue
            if re.search(r"(buyer|consignee|ship\s*to|bill\s*to|voucher|dated)", l, re.I):
                break
            addr_lines.append(l.strip())
    addr = ", ".join([a for a in addr_lines if a]) or None

    return {
        "name": (name or None),
        "gst_number": (gst or None),
        "address": addr,
        "contact": phone,
        "email": email,
    }

def parse_vendor_invoice_text(text: str) -> Dict[str, Any]:
    """
    Parse GST-style vendor invoices (like A2Z Buildwares Tiles & Sanitarywares).
    Returns:
      {
        vendor_name, voucher_no, invoice_date, bill_to, ship_to,
        subtotal, cgst, sgst, igst, other_charges, total,
        vendor: {name, gst_number, address, contact, email},
        lines: [{description, hsn, uom, qty, rate, discount_pct, amount}]
      }
    """
    data: Dict[str, Any] = {
        "vendor_name": None,
        "voucher_no": None,
        "invoice_date": None,
        "bill_to": None,
        "ship_to": None,
        "subtotal": Decimal("0"),
        "cgst": Decimal("0"),
        "sgst": Decimal("0"),
        "igst": Decimal("0"),
        "other_charges": Decimal("0"),
        "total": Decimal("0"),
        "vendor": None,
        "lines": [],
    }

    # ---- Vendor block (name/GST/address/phone/email) ----
    vblock = _extract_vendor_block(text)
    data["vendor"] = vblock
    data["vendor_name"] = vblock.get("name")

    # ---- Voucher/Invoice No ----
    m_voucher = re.search(
        r"(?:Voucher|Invoice)\s*No\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)",
        text,
        re.I,
    )
    data["voucher_no"] = m_voucher.group(1).strip() if m_voucher else None

    # ---- Invoice date ----
    m_date = re.search(
        r"(?:Dated|Date)\s*[:\-]?\s*([0-9]{1,2}[-/ ][A-Za-z]{3}[A-Za-z]?[-/ ][0-9]{2,4}|[0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})",
        text,
        re.I,
    )
    if m_date:
        rawd = m_date.group(1).replace(" ", "-")
        for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y"):
            try:
                data["invoice_date"] = datetime.strptime(rawd, fmt).date()
                break
            except Exception:
                pass

    # ---- Bill to / Ship to blocks (optional) ----
    m_bill = re.search(
        r"Buyer\s*\(Bill to\)\s*(.+?)(?:\n\s*\n|Voucher|Buyer’s Ref|Dated)",
        text,
        re.I | re.S,
    )
    if m_bill:
        data["bill_to"] = re.sub(r"\s+\n", " ", m_bill.group(1)).strip()

    m_ship = re.search(
        r"Consignee\s*\(Ship to\)\s*(.+?)(?:\n\s*\n|Buyer|Voucher|Dated)",
        text,
        re.I | re.S,
    )
    if m_ship:
        data["ship_to"] = re.sub(r"\s+\n", " ", m_ship.group(1)).strip()

    # ---- Taxes / totals ----
    m_cgst = re.search(r"\bCGST\b\s+" + INR_CAPTURE, text, re.I)
    m_sgst = re.search(r"\bSGST\b\s+" + INR_CAPTURE, text, re.I)
    m_igst = re.search(r"\bIGST\b\s+" + INR_CAPTURE, text, re.I)
    m_trans = re.search(r"(?:TRANSPORT|FREIGHT|DELIVERY).{0,20}\s" + INR_CAPTURE, text, re.I)
    m_total = re.search(r"(?:Grand\s*Total|Total)\s*[:\-]?\s*₹?\s*" + INR_CAPTURE + r"(?!\s*%)", text, re.I)

    data["cgst"] = _to_decimal(m_cgst.group(1) if m_cgst else None)
    data["sgst"] = _to_decimal(m_sgst.group(1) if m_sgst else None)
    data["igst"] = _to_decimal(m_igst.group(1) if m_igst else None)
    data["other_charges"] = _to_decimal(m_trans.group(1) if m_trans else None)
    data["total"] = _to_decimal(m_total.group(1) if m_total else None)

    if data["total"]:
        data["subtotal"] = (
            data["total"]
            - data["cgst"]
            - data["sgst"]
            - data["igst"]
            - data["other_charges"]
        )

    # ---- Line capture: SlNo  Desc  HSN  Qty  Rate  (Disc)  Amount ----
    # Flexible on missing HSN/Disc/Amount; infer amount if possible.
    line_re = re.compile(
        r"""
        ^\s*(\d{1,3})\s+                                 # SlNo
        (?P<desc>[A-Za-z0-9\-\*\s\/&\(\)\.,]+?)\s+       # Description
        (?:(?P<hsn>\d{4,8})\s+)?                         # optional HSN
        (?:(?:nos?|pcs?|PCS|NOS|Box|BOX)\s+)?            # optional unit label
        (?P<qty>\d{1,7}(?:\.\d{1,3})?)\s+                # Qty
        (?P<rate>\d{1,7}(?:\.\d{1,2})?)\s+               # Rate
        (?:(?:Disc\.?|Discount)\s*%?\s*(?P<disc>\d{1,2}(?:\.\d{1,2})?))?  # optional disc %
        \s*(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)? # optional amount
        $""",
        re.I | re.M | re.X,
    )

    for m in line_re.finditer(text):
        d = m.groupdict()
        uom = (
            "nos"
            if re.search(r"\bnos?\b", m.group(0), re.I)
            else ("pcs" if re.search(r"\bpcs?\b", m.group(0), re.I) else "")
        )
        qty = _to_decimal(d["qty"] or "0")
        rate = _to_decimal(d["rate"] or "0")
        disc = _to_decimal(d["disc"] or "0")
        amount = _to_decimal(d["amount"] or "0")

        if amount == 0 and qty and rate:
            amount = (qty * rate * (Decimal("100") - disc) / Decimal("100")).quantize(
                Decimal("0.01")
            )

        # sanity check (avoid absurd OCR)
        if not _is_sane(float(qty), float(rate), float(amount)):
            logger.info("[parse_vendor_invoice_text] skip insane line: %s", m.group(0)[:120])
            continue

        data["lines"].append(
            {
                "description": (d["desc"] or "").strip(),
                "hsn": (d["hsn"] or "").strip(),
                "uom": uom,
                "qty": qty,
                "rate": rate,
                "discount_pct": disc,
                "amount": amount,
            }
        )

    return data
def detect_vendor_from_text(raw_text: str) -> dict:
    """Split OCR text into lines and run vendor detector."""
    lines = [ln.strip() for ln in (raw_text or "").splitlines() if ln.strip()]
    return detect_vendor_from_lines(lines)

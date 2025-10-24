# app/ocr_pipeline.py
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import pdfplumber
from pdf2image import convert_from_path
import pytesseract

from app import models, crud
from .parsing import detect_vendor_from_text  # optional GST proximity helper

log = logging.getLogger(__name__)

# --------------------------- number / token patterns ---------------------------
# allow 0-3 decimals, optional thousands separators
DEC = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,3})?"
INT = r"\d{1,7}"
UOM = r"(?:NOS|PCS|BOX|SET|PAIR|PKT|ROLL|MTR|METER|LTR)"
# HSN must not be embedded in a larger token
HSN = r"(?<![A-Za-z0-9])(?P<hsn>\d{4,8})(?![A-Za-z0-9])"

# HSN ... Qty UOM Rate Amount  (gaps optional, UOM REQUIRED)
ITEM_PAT_HSN_QTY = re.compile(
    rf"(?P<desc>[A-Za-z0-9/\-\.\s\"]+?)\s+"
    rf"{HSN}\s+"
    rf"(?P<qty>{INT})\s*(?P<uom>{UOM})\s+"
    rf"(?P<rate>{DEC})\s*(?:{UOM})?\s+"
    rf"(?P<amount>{DEC})",
    re.I,
)

# Amount ... Rate Qty UOM ... HSN  (gaps optional, UOM REQUIRED with qty)
ITEM_PAT_AMOUNT_FIRST = re.compile(
    rf"(?P<amount>{DEC})\s*(?P<uom>{UOM})?\s+"
    rf"(?P<rate>{DEC})\s+"
    rf"(?P<qty>{INT})\s*(?P<uom2>{UOM})\s+"
    rf"{HSN}",
    re.I,
)

HEADER_NOISE = re.compile(
    r"^\s*(?:Sl\s*No\.?|No\.\s*|No\s+Goods\s+and\s+Services|Description\s+of\s+Goods.*|Amount\s*$)",
    re.I,
)

# --------------------------- metadata regex ---------------------------
GST_RE   = re.compile(r"(?:GSTIN|GST\s*No\.?|GSTIN/UIN)\s*[:\-]?\s*([0-9A-Z]{15})", re.I)
PHONE_RE = re.compile(r"(?:\+91[\-\s]?)?\b\d{10}\b|\b\d{3,5}[-\s]?\d{6,8}\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# invoice/bill numbers & dates (support "Invoice No:" on one line, value on next)
INVOICE_LABEL  = re.compile(r"(?:Invoice\s*(?:No\.?|#)|Bill\s*(?:No\.?|#))\s*[:\-]?\s*$", re.I)
INVOICE_INLINE = re.compile(r"(?:Invoice\s*(?:No\.?|#)|Bill\s*(?:No\.?|#))\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-\/\. ]{0,40})", re.I)
INVOICE_VALUE  = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-\/\. ]{0,40}$")

DATED_INLINE = re.compile(
    r"Dated\s*[:\-]?\s*([0-9]{1,2}[-/][A-Za-z]{3}[-/][0-9]{2,4}|[0-9]{2}[-/][0-9]{2}[-/][0-9]{2,4})",
    re.I,
)
DATE_TOKEN = re.compile(r"([0-9]{1,2}[-/][A-Za-z]{3}[-/][0-9]{2,4}|[0-9]{2}[-/][0-9]{2}[-/][0-9]{2,4})")

# Heuristics to detect invoice-like codes & month strings (avoid mislabeling vendor
# and to keep them out of item descriptions)
INVOICE_VALUEISH = re.compile(
    r"\b[A-Z0-9]{2,}(?:[\/\-][A-Z0-9]{1,}){1,}\b|\b\d{2,}[\/\-]\d{2,}(?:[\/\-]\d{2,})+\b",
    re.I,
)
MONTH_TOKEN = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|July?|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\b",
    re.I,
)

def _normalize_date(date_str: str) -> datetime.date | None:
    fmts = ("%d-%b-%y", "%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y-%m-%d")
    s = re.sub(r"(?i)\bdated\b[:\s]*", "", (date_str or "").strip())
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

# --------------------------- vendor heuristics ---------------------------
ALLCAPS_LINE = re.compile(r"^[A-Z0-9\s&\-.]{3,}$")

# strong positives for vendor names
POS_VENDOR_TOKENS = re.compile(
    r"(?:^A2Z\b|BUILDWARES?|TILE|TILES|SANIT|HARDWARE|CERAM|CERAMIC|BATH|PVT|LTD|LLP|CO\.?|COMPANY|ENTERPRISE|AGENC)",
    re.I,
)

# clear address-ish words; also typical header clutter
NEG_ADDRESS_TOKENS = re.compile(
    r"(GROUND|FLOOR|BLDG|BLDGS?|BUILDING|ASSOCIATION|MERCHANTS|NEAR|BANK|ROAD|RD\.?|STREET|ST\.?|LANE|POST|PO\b|PIN|STATE\s*NAME|KORATTY|THRISSUR|KERALA|EMAIL|E[-\s]?MAIL|PHONE|CONTRACTOR)",
    re.I,
)

# right pane labels; must not be treated as vendor/name/address
RIGHT_PANEL_LABELS = re.compile(
    r"(?:Tax\s*Invoice|Accounting\s*Voucher\s*Display|e[-\s]?Way\s*Bill|"
    r"Invoice\s*(?:No\.?|#)|Bill\s*(?:No\.?|#)|Dated|Delivery\s*Note|Mode/Terms|Reference\b|Buyer’s\s*Order|"
    r"Dispatch(?:ed)?\s*through|Other\s*References|Destination|Terms\s*of\s*Delivery|Page\s*\d+)",
    re.I,
)

# Prevent party/right-panel/header lines from leaking into product descriptions
DROP_IN_DESC = re.compile(
    r"(?:\bConsignee\b|\bBuyer\b|Invoice\s*(?:No\.?|#)|\bDated\b|"
    r"Terms\s*of\s*Delivery|Dispatched(?:ed)?\s*through|Destination|"
    r"Delivery\s*Note|Mode/Terms|Other\s*References|Buyer’s?\s*Order|"
    r"State\s*Name|GSTIN|GSTIN/UIN|Reference\b|E[-\s]?mail|Email|Page\s*\d+|Tax\s*Invoice|Accounting\s*Voucher\s*Display|Contractor)",
    re.I,
)

# obvious non-item text
ITEM_BLOCKLIST = re.compile(
    r"(?:\bGSTIN\b|\bState\s*Name\b|\bBuyer\b|\bConsignee\b|\bBank\b|\bIFSC\b|"
    r"\bTransportation\b|\bOUTPUT\s+(?:CGST|SGST)\b|\bDelivery\s*Note\b|"
    r"\bReference\b|continued\s*\.\.\.|Computer Generated Invoice|"
    r"^Amount\s*Chargeable\b|^Declaration\b|^Company’s Bank Details\b|^for\s+|"
    r"\bTax\s*Invoice\b|Accounting\s*Voucher\s*Display|^Page\s*\d+\b)",
    re.I,
)

# --------------------------- helpers ---------------------------
def _clean_commas(s: str | None) -> str:
    return re.sub(r"(?<=\d),(?=\d)", "", s or "")

def _to_float(s: str | None) -> Optional[float]:
    try:
        return float(_clean_commas(s))
    except Exception:
        return None

def _strip_noise(s: str) -> str:
    return (
        (s or "")
        .replace("|", " ")
        .replace("[", " ")
        .replace("INOS", " NOS ")
        .replace("  ", " ")
        .strip()
    )

def _validate_and_fix(qty: Optional[float], rate: Optional[float], amount: Optional[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if qty and rate and amount:
        if abs(qty * rate - amount) <= max(1.0, 0.05 * (amount or 0)):
            return qty, rate, amount
        # mis-placed columns: treat amount as rate
        if abs(qty * amount - (rate or 0)) <= max(1.0, 0.05 * (rate or 0)):
            return qty, amount, rate
    if qty and rate and not amount:
        return qty, rate, round(qty * rate, 2)
    if qty and amount and not rate and qty != 0:
        return qty, round(amount / qty, 2), amount
    return qty, rate, amount

def _is_mostly_numbers(ln: str) -> bool:
    letters = sum(c.isalpha() for c in ln)
    digits  = sum(c.isdigit() for c in ln)
    return digits > 0 and letters < 3

def _clean_desc(s: str) -> str:
    s = re.sub(r"\b(Sl\.?|No\.?|Description of|Goods and Services|Amount|HSN/SAC|HSN|SAC|Quantity|Qty|Rate|per|Disc\.?\s*%?)\b", " ", s, flags=re.I)
    s = re.sub(r"^\s*\d{1,3}\s+", " ", s)  # item index
    s = re.sub(r"\s+", " ", s)
    return s.strip(" :-,.")

def _pick_desc_lines(lines: List[str]) -> str:
    """
    Keep only the LAST 1–2 lines just before the numeric tail.
    Drop all-caps person/org lines with no digits, and any party/right-panel or address/email/invoice-code crumbs.
    """
    if not lines:
        return ""
    kept: List[str] = []
    for ln in reversed(lines):
        l = (ln or "").strip()
        if not l:
            continue
        # hard filters to avoid header/side-panel leakage
        if (DROP_IN_DESC.search(l)
            or RIGHT_PANEL_LABELS.search(l)
            or ITEM_BLOCKLIST.search(l)
            or HEADER_NOISE.search(l)
            or EMAIL_RE.search(l)
            or NEG_ADDRESS_TOKENS.search(l)
            or INVOICE_VALUEISH.search(l)
            or DATE_TOKEN.search(l)
            or MONTH_TOKEN.search(l)):
            continue
        # drop pure ALL-CAPS names with no digits/symbol cues
        if ALLCAPS_LINE.match(l) and not re.search(r"\d|[*\"/:-]", l):
            continue
        if _is_mostly_numbers(l):
            continue
        kept.append(l)
        if len(kept) >= 2:
            break
    kept.reverse()
    return _clean_desc(" ".join(kept))

# --------------------------- text extraction ---------------------------
def _extract_text_textlayer(file_path: str) -> str:
    pages_text = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=1.5, y_tolerance=2.0) or ""
            pages_text.append(t)
    return "\n".join(pages_text)

def _extract_text_ocr(file_path: str, dpi: int = 300) -> str:
    pages = convert_from_path(file_path, dpi=dpi)
    out = []
    for i, pg in enumerate(pages):
        try:
            out.append(pytesseract.image_to_string(pg, config="--psm 6 --oem 1"))
        except Exception as e:
            log.warning("OCR failed on page %s: %s", i + 1, e)
    return "\n".join(out)

def extract_text_from_pdf(file_path: str) -> str:
    try:
        text = _extract_text_textlayer(file_path)
        if len(text or "") >= 150:
            return text
    except Exception:
        log.exception("pdfplumber failed, falling back to OCR")
    try:
        return _extract_text_ocr(file_path)
    except Exception:
        log.exception("OCR failed")
        return ""

# --------------------------- vendor / invoice/date helpers ---------------------------
def _slice_header_before_parties(text: str) -> str:
    """
    Return all text before 'Consignee' / 'Buyer' blocks (keeps left + right top panels).
    """
    pos = len(text or "")
    for anchor in (r"Consignee\s*\(Ship\s*to\)", r"Buyer\s*\(Bill\s*to\)"):
        m = re.search(anchor, text or "", re.I)
        if m:
            pos = min(pos, m.start())
    return (text or "")[:pos]

def _extract_invoice_no(text: str) -> Optional[str]:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    for i, ln in enumerate(lines):
        m_inline = INVOICE_INLINE.search(ln)
        if m_inline:
            v = (m_inline.group(1) or "").strip()
            if v:
                return re.sub(r"\s+$", "", v)
        if INVOICE_LABEL.search(ln):
            for j in range(i + 1, min(i + 4, len(lines))):
                cand = lines[j].strip()
                if not cand:
                    continue
                if INVOICE_VALUE.match(cand) or re.search(r"[A-Z0-9]+[-/][A-Z0-9/ -]+", cand):
                    return cand
            break
    return None

def _extract_bill_date(text: str) -> Optional[str]:
    m = DATED_INLINE.search(text or "")
    if m:
        return m.group(1)
    for m in re.finditer(r"\bDated\b[:\s\-]*([^\n]*)", text or "", re.I):
        tail = m.group(1) or ""
        mm = DATE_TOKEN.search(tail)
        if mm:
            return mm.group(1)
        after = (text or "")[m.end():].splitlines()[:3]
        for ln in after:
            mm2 = DATE_TOKEN.search(ln)
            if mm2:
                return mm2.group(1)
    return None

def _canonicalize_vendor(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    # normalize common OCR variants
    s = re.sub(r"(?i)\bA\s*[- ]?\s*2\s*[- ]?\s*Z\b", "A2Z", s)
    s = re.sub(r"(?i)BUILDW\w*R\w*ES?", "BUILDWARES", s)  # handles BUILDWRAES/BUILDWREAS/etc.
    # tidy casing; keep acronyms
    titled = s.title()
    return titled.replace("A2Z", "A2Z").replace("Llp", "LLP").replace("Pvt", "Pvt").strip(" -,. /")

def _sanitize_vendor_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return name
    s = name.strip()
    # Drop anything after a clear date token
    s = re.sub(r"\b\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}\b.*$", "", s)
    if MONTH_TOKEN.search(s):
        m = MONTH_TOKEN.search(s)
        if m:
            s = s[:m.start()]
    # If there is an invoice-like code after a space, trim the trailing part
    s = re.sub(r"\s+(?:[A-Za-z0-9]+[\/\-]){1,}[A-Za-z0-9\-\/]+.*$", "", s)
    # Avoid chopping A2Z itself: only trim digits when preceded by space
    s = re.sub(r"\s+\d.*$", "", s)
    return _canonicalize_vendor(s.strip(" -,. /"))

def _best_vendor_name(header_lines: List[str]) -> Optional[Tuple[int, str]]:
    """
    Scan the first ~35 non-empty lines of the header (before Consignee/Buyer),
    ignoring right-panel labels, and score each candidate.
    """
    scan = [ln for ln in header_lines[:35] if not RIGHT_PANEL_LABELS.search(ln)]
    best_idx, best_score = None, -10**9
    for i, ln in enumerate(scan):
        raw = ln.strip()
        if not raw:
            continue

        # immediate skip: looks like invoice code / dates / address-ish tokens
        if INVOICE_VALUEISH.search(raw) or DATE_TOKEN.search(raw) or MONTH_TOKEN.search(raw):
            continue
        if NEG_ADDRESS_TOKENS.search(raw):
            continue

        score = 0
        if ALLCAPS_LINE.match(raw): score += 8
        score += 14 * len(POS_VENDOR_TOKENS.findall(raw))   # strong boost for vendor-ish tokens
        if i <= 2: score += 6

        if EMAIL_RE.search(raw): score -= 30
        if re.search(r"\bGST(?:IN)?\b|STATE\s*NAME", raw, re.I): score -= 30
        if raw.count("/") >= 2 and any(c.isdigit() for c in raw): score -= 40
        if re.search(r"\b\d{2}\s*-\s*\d{2}\b", raw): score -= 25  # 25-26, etc.

        if score > best_score:
            best_idx, best_score = i, score

    if best_idx is None:
        return (None, None)

    name = _sanitize_vendor_name(scan[best_idx])
    return (best_idx, name) if name else (None, None)

def _extract_vendor_from_header(text: str) -> Dict[str, Optional[str]]:
    header = _slice_header_before_parties(text)
    lines = [ln.strip() for ln in header.splitlines() if ln.strip()]

    name_idx, name = _best_vendor_name(lines)

    # Blob limited to header (before Consignee/Buyer)
    window_blob = "\n".join(lines)

    gst_match = GST_RE.search(window_blob)
    gst = gst_match.group(1) if gst_match else None

    # normalize phones to +91XXXXXXXXXX where possible
    phones = PHONE_RE.findall(window_blob) or []
    norm: List[str] = []
    for p in phones:
        digits = re.sub(r"[^\d+]", "", p)
        if digits.startswith("+91"):
            digits = "+91" + re.sub(r"^\+91", "", digits)[-10:]
        elif len(digits) >= 10:
            digits = "+91" + digits[-10:]
        if digits not in norm:
            norm.append(digits)
    phone = ", ".join(norm) if norm else None
    email = (EMAIL_RE.search(window_blob).group(0) if EMAIL_RE.search(window_blob) else None)

    # build address under the chosen name, but stop at right-panel/labels/phones
    address = None
    if name and name in lines:
        idx = lines.index(name)
        block: List[str] = []
        for ln in lines[idx + 1: idx + 10]:
            if (RIGHT_PANEL_LABELS.search(ln) or
                re.search(r"(GST|GSTIN|Invoice|Bill\s*No|Dated|Phone|E[-\s]?mail|Buyer|Consignee|Delivery|Reference|Dispatch|Terms|State\s*Name)", ln, re.I)):
                break
            # skip phone-only or long numbery lines
            if PHONE_RE.search(ln) or re.fullmatch(r"\d[\d\s,\-]+", ln):
                continue
            block.append(ln)
        if block:
            address = ", ".join(block)

    name = _sanitize_vendor_name(name)

    return {"name": name, "gst_number": gst, "address": address, "email": email, "phone": phone}

def _merge_vendor_guess(header_pick: Dict[str, Optional[str]], vd: Dict[str, Any]) -> Dict[str, Any]:
    """
    IMPORTANT: Never override the name chosen from the header.
    Only fill GST if header pick lacks it.
    """
    out = dict(header_pick or {})
    if (not out.get("gst_number")) and vd.get("gstin"):
        out["gst_number"] = vd["gstin"]
    return out

# --------------------------- table extraction ---------------------------
def _header_index_map(cols: List[str]) -> Dict[str, Optional[int]]:
    """
    Best-effort header mapping for a row. Returns indices for sl, desc, hsn, qty, rate, amount.
    """
    low = [(c or "").strip().lower() for c in cols]
    def find(*tokens):
        for i, c in enumerate(low):
            for t in tokens:
                if t in c:
                    return i
        return None
    return {
        "sl": find("sl", "no.", "no"),
        "desc": find("description", "goods", "services", "item"),
        "hsn": find("hsn", "sac", "hsn/sac"),
        "qty": find("qty", "quantity"),
        "rate": find("rate", "price"),
        "amount": find("amount", "amt", "value", "total"),
    }

def _coalesce_desc(cell: str | None) -> str:
    return _clean_desc((cell or "").replace("\n", " ").replace("\r", " "))

def _extract_table_items(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract line items from visible tables. If we can map a header row, we use that mapping;
    otherwise assume the common order: [Sl, Desc, HSN, Qty, Rate, ..., Amount].
    """
    out: List[Dict[str, Any]] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                    "intersection_tolerance": 3,
                    "edge_min_length": 15,
                }) or []
                for tbl in tables:
                    if not tbl or len(tbl) == 0:
                        continue

                    # Try header mapping if the first non-empty row looks like header
                    header_row = None
                    for r in tbl[:3]:
                        if r and any(isinstance(c, str) and re.search(r"(desc|hsn|qty|rate|amount|no)", (c or "").lower()) for c in r):
                            header_row = r
                            break
                    idx = _header_index_map(header_row) if header_row else None

                    for row in tbl:
                        cols = [c.strip() if isinstance(c, str) else "" for c in row]
                        if not any(cols):
                            continue

                        # If the row is the detected header, skip
                        if header_row and cols == [c.strip() if isinstance(c, str) else "" for c in header_row]:
                            continue

                        # Map columns
                        if idx and all(idx.get(k) is not None for k in ("desc", "hsn", "qty", "rate", "amount")):
                            sl      = cols[idx["sl"]] if idx.get("sl") is not None and idx["sl"] < len(cols) else ""
                            desc    = cols[idx["desc"]] if idx["desc"] < len(cols) else ""
                            hsn     = cols[idx["hsn"]] if idx["hsn"] < len(cols) else ""
                            qty     = cols[idx["qty"]] if idx["qty"] < len(cols) else ""
                            rate    = cols[idx["rate"]] if idx["rate"] < len(cols) else ""
                            amount  = cols[idx["amount"]] if idx["amount"] < len(cols) else cols[-1]
                        else:
                            # Fallback to conventional positions
                            if len(cols) < 5:
                                continue
                            sl, desc, hsn, qty = cols[0], cols[1], cols[2], cols[3]
                            rate = cols[4]
                            amount = cols[-1]

                        # Row sanity
                        if sl and not re.fullmatch(r"\d{1,3}", re.sub(r"\D", "", sl) or ""):
                            # many PDFs have blank/merged slno; don't enforce too hard
                            pass

                        qtyf, ratef = _to_float(qty), _to_float(rate)
                        amtf = _to_float(amount)
                        qtyf, ratef, amtf = _validate_and_fix(qtyf, ratef, amtf)
                        if qtyf and (ratef or amtf):
                            out.append({
                                "description_raw": _coalesce_desc(desc),
                                "hsn": re.sub(r"\D", "", hsn) or None,
                                "qty": float(qtyf or 0),
                                "unit_price": float(ratef or 0),
                                "line_total": float(amtf or 0),
                                "uom": None,
                                "ocr_confidence": 0.985,
                            })
    except Exception:
        log.exception("table extraction failed")
    return out

# --------------------------- line parsing from text (order-aware) ---------------------------
def _parse_items(text: str) -> List[Dict[str, Any]]:
    s = _strip_noise(re.sub(r"(\d),(\d)", r"\1\2", text or ""))

    findings: List[Tuple[str, int, int, re.Match]] = []
    for m in ITEM_PAT_AMOUNT_FIRST.finditer(s):
        findings.append(("AMT", m.start(), m.end(), m))
    for m in ITEM_PAT_HSN_QTY.finditer(s):
        findings.append(("HSN", m.start(), m.end(), m))

    if not findings:
        return []

    findings.sort(key=lambda t: t[1])

    items: List[Dict[str, Any]] = []
    prev_end = 0

    for kind, start, end, m in findings:
        seg = s[prev_end:start]
        seg_lines = [ln.strip() for ln in seg.splitlines() if ln.strip()]
        desc_left = _pick_desc_lines(seg_lines)

        d = m.groupdict()

        qty, rate, amount = _validate_and_fix(_to_float(d["qty"]), _to_float(d["rate"]), _to_float(d["amount"]))
        if kind == "AMT":
            uom = (d.get("uom2") or d.get("uom") or "").upper() or None
            hsn = d["hsn"]
            desc = desc_left
        else:
            uom = (d.get("uom") or "").upper() or None
            hsn = d["hsn"]
            desc = _clean_desc((desc_left + " " + (d.get("desc") or "")).strip())

        if not desc or ITEM_BLOCKLIST.search(desc) or DROP_IN_DESC.search(desc):
            prev_end = end
            continue

        items.append({
            "description_raw": desc,
            "qty": float(qty or 0),
            "uom": uom,
            "unit_price": float(rate or 0),
            "line_total": float(amount or 0),
            "hsn": hsn,
            "ocr_confidence": 0.93 if kind == "AMT" else 0.95,
        })
        prev_end = end

    return items

def _dedup_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for li in items:
        key = (
            (li.get("description_raw") or "").lower().strip()[:160],
            round(float(li.get("qty") or 0), 3),
            round(float(li.get("unit_price") or 0), 3),
            round(float(li.get("line_total") or 0), 2),
            (li.get("hsn") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(li)
    return out

# --------------------------- totals + metadata ---------------------------
CGST_RE = re.compile(r"\bCGST\b\s+(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)", re.I)
SGST_RE = re.compile(r"\bSGST\b\s+(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)", re.I)
IGST_RE = re.compile(r"\bIGST\b\s+(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)", re.I)
TOTAL_RE = re.compile(r"(?:Grand\s*Total|Total\s*Amount|Total)\s*₹?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)", re.I)

def parse_invoice_text(text: str) -> Dict[str, Any]:
    items = _parse_items(text)

    totals: Dict[str, float] = {}
    if (m := CGST_RE.search(text)): totals["cgst"] = _to_float(m.group(1)) or 0.0
    if (m := SGST_RE.search(text)): totals["sgst"] = _to_float(m.group(1)) or 0.0
    if (m := IGST_RE.search(text)): totals["igst"] = _to_float(m.group(1)) or 0.0
    # Prefer the largest plausible "Total" on the page (handles multiple matches)
    ms = list(TOTAL_RE.finditer(text))
    if ms:
        totals["grand_total"] = max(
            (_to_float(m.group(1)) or 0.0) for m in ms
        )


    md: Dict[str, Any] = {}

    inv = _extract_invoice_no(text)
    if inv and inv.lower() != "dated" and re.search(r"\d", inv):
        md["invoice_no"] = inv.strip()

    if (dstr := _extract_bill_date(text)):
        d = _normalize_date(dstr)
        if d:
            md["bill_date"] = d.isoformat()

    # --- vendor: STRICT header only; detector only fills missing GST ---
    header_vendor = _extract_vendor_from_header(text)
    header = _slice_header_before_parties(text)
    vd = detect_vendor_from_text(header)  # optional helper for GST
    v = _merge_vendor_guess(header_vendor, vd)

    md["vendor_name"] = v.get("name")
    md["gst_number"]  = v.get("gst_number")
    md["address"]     = v.get("address")
    if header_vendor.get("email"): md["email"] = header_vendor["email"]
    if header_vendor.get("phone"): md["phone"] = header_vendor["phone"]

    # diagnostics
    if vd.get("pos_state_code"): md["pos_state_code"] = vd["pos_state_code"]
    if vd.get("pos_state_name"): md["pos_state_name"] = vd["pos_state_name"]
    md["vendor_confidence"] = vd.get("score")
    md["vendor_source"]     = vd.get("source")
    md["needs_review_vendor"] = bool(vd.get("needs_review"))

    return {"lines": items, "totals": totals, "metadata": md}

# --------------------------- plausibility guard ---------------------------
def _looks_plausible(li: Dict[str, Any]) -> bool:
    desc = (li.get("description_raw") or "").strip()
    if not desc or ITEM_BLOCKLIST.search(desc) or DROP_IN_DESC.search(desc):
        return False
    try:
        qty = float(li.get("qty") or 0)
        rate = float(li.get("unit_price") or 0)
        amt  = float(li.get("line_total") or 0)
    except Exception:
        return False
    if qty <= 0 or rate < 0 or amt < 0:
        return False
    if qty > 1_000_000 or rate > 1_000_000 or amt > 10_000_000:
        return False
    return True

# --------------------------- continuation repair & totals recompute ---------------------------
DIM_TOKEN = re.compile(
    r"""^(
        \d{2,4}\s*MM|            # 220MM, 450 MM
        \d{1,3}\s*CM|            # 80 CM
        \d{1,2}\s*(?:["”])|      # 18", 24”
        \d{2,4}\s*\*\s*\d{2,4}\s*CM|  # 80*65 CM (OCR star)
        \d{1,4}x\d{1,4}          # 600x600
    )\b""",
    re.IGNORECASE | re.VERBOSE
)
SNO_TOKEN = re.compile(r"^\s*(\d{1,3})\s+\b")

def _normalize_quotes_spaces(s: str) -> str:
    s = (s or "").replace('”','"').replace('“','"').replace('′',"'")
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+(CM|MM)\b", r" \1", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\*\s*", "* ", s)  # "80* 65 CM" -> "80* 65 CM"
    s = re.sub(r'\s+"', '"', s)
    return s.strip()

def _repair_continuations(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge leading dimension tokens (e.g., '220MM', '24"') into previous line's description.
    Lift S.No to the head if it appears later in the string.
    """
    out: List[Dict[str, Any]] = []
    for i, ln in enumerate(lines):
        curr = dict(ln)
        desc = _normalize_quotes_spaces(curr.get("description_raw") or "")

        # If this line begins with a dimension token, push the token into previous desc
        m = DIM_TOKEN.match(desc)
        if m and out:
            dim = m.group(1).strip()
            prev = dict(out[-1])
            pdesc = _normalize_quotes_spaces(prev.get("description_raw") or "")
            if not re.search(rf"\b{re.escape(dim)}\b", pdesc, flags=re.IGNORECASE):
                prev["description_raw"] = (pdesc + " " + dim).strip()
            out[-1] = prev
            desc = desc[m.end():].lstrip()

        # If a serial number exists away from the head, move it to the front
        if not SNO_TOKEN.match(desc):
            tail_sno = re.search(r"\b(\d{1,3})\b\s+(?=[A-Z0-9])", desc)
            if tail_sno:
                sno = tail_sno.group(1)
                desc = f"{sno} " + re.sub(r"\b" + re.escape(sno) + r"\b\s+", "", desc, count=1)

        curr["description_raw"] = desc.strip()
        out.append(curr)
    return out

def _recompute_line_totals(lines: List[Dict[str, Any]], tolerance: float = 0.50) -> Tuple[List[Dict[str, Any]], float, bool]:
    """
    Recompute each line_total as qty*unit_price (2dp). If existing line_total differs within tolerance, fix it.
    Returns (lines, sum_total, any_line_flagged).
    """
    from decimal import Decimal, ROUND_HALF_UP
    sum_calc = Decimal("0.00")
    any_flag = False
    out: List[Dict[str, Any]] = []
    for ln in lines:
        li = dict(ln)
        try:
            qty = Decimal(str(li.get("qty") or 0))
            up  = Decimal(str(li.get("unit_price") or 0))
            expected = (qty * up).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            seen = Decimal(str(li.get("line_total") or 0)).quantize(Decimal("0.01"))
            if (expected - seen).copy_abs() <= Decimal(str(tolerance)):
                li["line_total"] = float(expected)
            else:
                # keep existing, but flag
                li["needs_review"] = True
                any_flag = True
            sum_calc += expected
        except Exception:
            any_flag = True
        out.append(li)
    return out, float(sum_calc), any_flag

# --------------------------- orchestrator ---------------------------
def _prefer_table_lines(lines_text: List[Dict[str, Any]], lines_table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    If we detected a reasonable table (>=3 plausible rows OR sum>0), prefer those lines exclusively.
    This prevents cross-row bleeding like '220MM' drifting into the next item.
    """
    table_plausible = [li for li in lines_table if _looks_plausible(li)]
    if len(table_plausible) >= 3 or round(sum(float(li.get("line_total") or 0) for li in table_plausible), 2) > 0:
        return table_plausible
    # otherwise, keep both
    return [li for li in (lines_text + lines_table) if _looks_plausible(li)]

def process_invoice(file_path: str, db, bill_id: int) -> Dict[str, Any]:
    text = extract_text_from_pdf(file_path)
    parsed = parse_invoice_text(text)

    # Extract tables then choose best line set
    lines_text  = parsed["lines"]
    lines_table = _extract_table_items(file_path)
    chosen_lines = _prefer_table_lines(lines_text, lines_table)

    # --- repair continuations / normalize serials (only helpful for text-derived noise) ---
    repaired_lines = _repair_continuations(chosen_lines)

    # Dedup after repairs
    merged_lines = _dedup_items(repaired_lines)

    # --- recompute line totals and capture possible discrepancies ---
    merged_lines, sum_lines_recomp, any_line_flag = _recompute_line_totals(merged_lines)

    # --- auto totals guard / reconciliation ---
    totals = dict(parsed["totals"] or {})
    taxes = sum(float(totals.get(k) or 0.0) for k in ("cgst", "sgst", "igst"))
    gt_stated = totals.get("grand_total")

    if gt_stated is None and sum_lines_recomp > 0:
        totals["grand_total"] = sum_lines_recomp
        totals["grand_total_source"] = "sum_of_lines"
    else:
        totals["grand_total_source"] = "stated"

    tol = max(1.0, 0.03 * max(sum_lines_recomp + taxes, totals.get("grand_total") or 0.0))
    needs_review_totals = False
    if totals.get("grand_total") is not None:
        expected = sum_lines_recomp + taxes
        if abs((totals["grand_total"] or 0) - expected) > tol:
            needs_review_totals = True

    # Compare raw text vs table sums to catch drift
    try:
        text_sum  = round(sum(float(li.get("line_total") or 0) for li in lines_text), 2)
        table_sum = round(sum(float(li.get("line_total") or 0) for li in lines_table), 2)
        if text_sum > 0 and table_sum > 0:
            delta = abs(text_sum - table_sum)
            if delta > max(1.0, 0.10 * max(text_sum, table_sum)):
                needs_review_totals = True
    except Exception:
        pass

    # persist lines (with plausibility guard)
    saved = 0
    for li in merged_lines:
        if not _looks_plausible(li):
            continue
        db.add(models.BillLine(
            bill_id=bill_id,
            description_raw=li.get("description_raw"),
            qty=li.get("qty"),
            unit_price=li.get("unit_price"),
            line_total=li.get("line_total"),
            ocr_confidence=li.get("ocr_confidence"),
            **({"uom": li.get("uom")} if hasattr(models.BillLine, "uom") else {}),
            **({"hsn": li.get("hsn")} if hasattr(models.BillLine, "hsn") else {}),
        ))
        saved += 1

    bill = db.get(models.Bill, bill_id)

    # Sum from parsed items currently in DB
    line_sum = 0.0
    try:
        line_sum = float(sum(
            (ln.line_total or 0.0)
            for ln in db.query(models.BillLine).filter_by(bill_id=bill_id).all()
        ))
    except Exception:
        line_sum = 0.0

    text_total = totals.get("grand_total")

    def _round2(x): 
        return None if x is None else float(round(x, 2))

    # Choose the most reasonable total:
    # 1) If both exist and disagree a lot, trust lines (and flag for review)
    # 2) If only one exists, use it
    # 3) Else leave as None
    if text_total is not None and line_sum > 0:
        # Allow ~20% room (GST, rounding, misc charges). Outside that → use lines.
        low, high = 0.8 * line_sum, 1.2 * line_sum
        if text_total < low or text_total > high:
            bill.total = _round2(line_sum)
            bill.needs_review = True
        else:
            bill.total = _round2(text_total)
    elif line_sum > 0:
        bill.total = _round2(line_sum)
    elif text_total is not None:
        bill.total = _round2(text_total)
    # else: keep as None


    md = parsed["metadata"] or {}
    if md.get("invoice_no"):
        bill.bill_no = md["invoice_no"]
    if md.get("bill_date"):
        try:
            bill.bill_date = datetime.fromisoformat(md["bill_date"]).date()
        except Exception:
            pass

    # ✅ attach vendor (crud will smart-upgrade existing row if GST matches)
    vendor_info = {
        "name": md.get("vendor_name"),
        "gst_number": md.get("gst_number"),
        "address": md.get("address"),
        "contact": md.get("phone") or md.get("contact"),
        "email": md.get("email"),
    }
    try:
        crud.attach_vendor_to_bill(db, bill, vendor_info)
    except Exception:
        log.exception("Vendor attach failed; leaving vendor_id unchanged")

    bill.status = "PROCESSED"

    needs_review = bool(md.get("needs_review_vendor") or needs_review_totals or any_line_flag)
    try:
        fname = os.path.basename(file_path)
        stem = os.path.splitext(fname)[0].strip().lower()
        inv = (md.get("invoice_no") or "").strip().lower()
        if inv and stem and (inv == fname.lower() or inv == stem):
            needs_review = True
    except Exception:
        pass

    if needs_review:
        try:
            setattr(bill, "needs_review", True)
        except Exception:
            pass

    db.commit()

    return {
        "bill_id": bill_id,
        "status": "PROCESSED",
        "lines_saved": saved,
        "totals": totals,
        "metadata": md,
        "needs_review": bool(needs_review),
    }

# init: add module header and logger (marker)

# chore: add stdlib imports (os, re, datetime, typing) (marker)

# feat: add third-party libraries (pdfplumber, pdf2image, pytesseract) (marker)

# feat: wire internal models/crud and parsing helper (marker)

# feat: add DEC/INT/UOM/HSN regex primitives (marker)

# feat: add HSN/Qty/UOM/Rate/Amount line regex (marker)

# feat: add amount-first item line regex (marker)

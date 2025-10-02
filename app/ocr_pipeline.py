# app/ocr_pipeline.py
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import pdfplumber
from pdf2image import convert_from_path
import pytesseract

from app import models, crud

log = logging.getLogger(__name__)

# --------------------------- helpers ---------------------------
def _clean_commas(s: str | None) -> str:
    return re.sub(r"(?<=\d),(?=\d)", "", s or "")

def _to_float(s: str | None) -> Optional[float]:
    try:
        return float(_clean_commas(s))
    except Exception:
        return None

def _normalize_date(date_str: str) -> datetime.date | None:
    fmts = ("%d-%b-%y", "%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y-%m-%d")
    s = (date_str or "").strip()
    s = re.sub(r"(?i)\bdated\b[:\s]*", "", s).strip()
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
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

# --------------------------- metadata regex ---------------------------
GST_RE  = re.compile(r"(?:GSTIN|GST\s*No\.?|GSTIN/UIN)\s*[:\-]?\s*([0-9A-Z]{15})", re.I)
PHONE_RE = re.compile(r"(?:\+91[\-\s]?)?\b\d{10}\b|\b\d{3,5}[-\s]?\d{6,8}\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
INVOICE_NO_RE = re.compile(r"(?:Invoice\s*(?:No\.?|#)|Bill\s*(?:No\.?|#))\s*[:\-]?\s*([A-Za-z0-9\-\/]+)", re.I)
DATE_RE = re.compile(r"(?:Dated\s*)?(\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}|\d{2}[-/]\d{2}[-/]\d{2,4})")

ALLCAPS_LINE = re.compile(r"^[A-Z0-9\s&\-.]{3,}$")
POS_VENDOR_TOKENS = re.compile(r"(BUILDWARE|TILE|SANIT|TRADER|HARDWARE|CERAM|PVT|LTD|LLP|CO\.?|COMPANY|ENTERPRISE|AGENC)", re.I)
NEG_ADDRESS_TOKENS = re.compile(r"(NEAR|BANK|ROAD|RD\.?|STREET|ST\.?|LANE|POST|PO\b|PIN|PH|MOB|PHONE|EMAIL)", re.I)

# --------------------------- item patterns ---------------------------
DEC = r"\d{1,3}(?:,\d{3})*\.\d{2}"
INT = r"\d{1,6}"
UOM = r"(?:NOS|PCS)"
HSN = r"(?<![A-Za-z])(?P<hsn>\d{4,8})(?!\d)"   # avoid picking digits from codes like F1019661

ITEM_PAT_HSN_QTY = re.compile(
    rf"(?P<desc>[A-Za-z0-9/\-\.\s\"]+?)\s+"
    rf"{HSN}\s+"
    rf"(?P<qty>{INT})\s*(?P<uom>{UOM})\s+"
    rf"(?P<rate>{DEC})\s*(?:{UOM})?\s+"
    rf"(?P<amount>{DEC})",
    re.I,
)
ITEM_PAT_AMOUNT_FIRST = re.compile(
    rf"(?P<amount>{DEC})\s*(?P<uom>{UOM})?\s+"
    rf"(?P<rate>{DEC})\s+"
    rf"(?P<qty>{INT})\s*(?P<uom2>{UOM})?\s+"
    rf"{HSN}",
    re.I,
)

# totals
CGST_RE = re.compile(r"\bCGST\b\s+(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)", re.I)
SGST_RE = re.compile(r"\bSGST\b\s+(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)", re.I)
IGST_RE = re.compile(r"\bIGST\b\s+(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)", re.I)
TOTAL_RE = re.compile(r"(?:Grand\s*Total|Total\s*Amount|Total)\s*₹?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)", re.I)

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

# --------------------------- vendor / parties ---------------------------
def _slice_header_before_parties(text: str) -> str:
    pos = len(text)
    for anchor in (r"Buyer\s*\(Bill\s*to\)", r"Consignee\s*\(Ship\s*to\)"):
        m = re.search(anchor, text, re.I)
        if m:
            pos = min(pos, m.start())
    return text[:pos]

def _guess_vendor(text: str) -> Dict[str, Optional[str]]:
    header = _slice_header_before_parties(text)
    header_lines = [ln.strip() for ln in header.splitlines() if ln.strip()]

    candidates = [ln for ln in header_lines[:15] if ALLCAPS_LINE.match(ln)]
    scored: List[Tuple[int,str]] = []
    for ln in candidates:
        score = 0
        if POS_VENDOR_TOKENS.search(ln): score += 2
        if NEG_ADDRESS_TOKENS.search(ln): score -= 2
        score += min(3, len(ln.split()))
        scored.append((score, ln))
    scored.sort(reverse=True)
    name = scored[0][1] if scored else (header_lines[0] if header_lines else "Unknown Vendor")

    gst_match = GST_RE.search(header)
    gst = gst_match.group(1) if gst_match else None

    address = None
    if name in header_lines:
        idx = header_lines.index(name)
        block = []
        for ln in header_lines[idx + 1 : idx + 8]:
            if re.search(r"(GST|GSTIN|Invoice|Bill\s*No|Dated|Phone|E[-\s]?mail|Buyer|Consignee)", ln, re.I):
                break
            if PHONE_RE.search(ln) and len(ln) < 24:
                continue
            block.append(ln)
        if block:
            address = ", ".join(block)

    email = (EMAIL_RE.search(header).group(0) if EMAIL_RE.search(header) else None)
    phones = PHONE_RE.findall(header)
    phone = ", ".join(sorted(set(phones))) if phones else None

    return {"name": name, "gst_number": gst, "address": address, "email": email, "phone": phone}

# --------------------------- items ---------------------------
def _validate_and_fix(qty: Optional[float], rate: Optional[float], amount: Optional[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if qty and rate and amount:
        if abs(qty * rate - amount) <= max(1.0, 0.05 * amount):
            return qty, rate, amount
        if abs(qty * amount - rate) <= max(1.0, 0.05 * rate):
            return qty, amount, rate
    if qty and rate and not amount:
        return qty, rate, round(qty * rate, 2)
    return qty, rate, amount

def _parse_items(text: str) -> List[Dict[str, Any]]:
    s = _strip_noise(re.sub(r"(\d),(\d)", r"\1\2", text or ""))
    items: List[Dict[str, Any]] = []

    for m in ITEM_PAT_HSN_QTY.finditer(s):
        d = m.groupdict()
        qty, rate, amount = _validate_and_fix(_to_float(d["qty"]), _to_float(d["rate"]), _to_float(d["amount"]))
        items.append({
            "description_raw": d["desc"].strip(),
            "qty": float(qty or 0),
            "uom": (d["uom"] or "").upper() or None,
            "unit_price": float(rate or 0),
            "line_total": float(amount or 0),
            "hsn": d["hsn"],
            "ocr_confidence": 0.95,
        })

    covered = [(m.start(), m.end()) for m in ITEM_PAT_HSN_QTY.finditer(s)]
    def _overlaps(a: Tuple[int,int]) -> bool:
        return any(not (a[1] <= b0 or a[0] >= b1) for (b0,b1) in covered)

    for m in ITEM_PAT_AMOUNT_FIRST.finditer(s):
        if _overlaps((m.start(), m.end())):
            continue
        d = m.groupdict()
        qty, rate, amount = _validate_and_fix(_to_float(d["qty"]), _to_float(d["rate"]), _to_float(d["amount"]))
        left = s[max(0, m.start() - 140): m.start()].split("\n")[-1]
        desc = re.sub(r"\s+", " ", left).strip(" :-,")
        uom = (d.get("uom2") or d.get("uom") or "").upper() or None
        items.append({
            "description_raw": desc,
            "qty": float(qty or 0),
            "uom": uom,
            "unit_price": float(rate or 0),
            "line_total": float(amount or 0),
            "hsn": d["hsn"],
            "ocr_confidence": 0.90,
        })

    return items

# --------------------------- high-level parse ---------------------------
def parse_invoice_text(text: str) -> Dict[str, Any]:
    items = _parse_items(text)

    totals: Dict[str, float] = {}
    if (m := CGST_RE.search(text)): totals["cgst"] = _to_float(m.group(1)) or 0.0
    if (m := SGST_RE.search(text)): totals["sgst"] = _to_float(m.group(1)) or 0.0
    if (m := IGST_RE.search(text)): totals["igst"] = _to_float(m.group(1)) or 0.0
    if (m := TOTAL_RE.search(text)): totals["grand_total"] = _to_float(m.group(1)) or 0.0

    md: Dict[str, Any] = {}
    if (m := DATE_RE.search(text)):
        d = _normalize_date(m.group(1))
        if d: md["bill_date"] = d.isoformat()

    if (m := INVOICE_NO_RE.search(text)):
        val = (m.group(1) or "").strip()
        if val and val.lower() != "dated" and re.search(r"\d", val):
            md["invoice_no"] = val

    v = _guess_vendor(text)
    md["vendor_name"] = v.get("name")
    md["gst_number"] = v.get("gst_number")
    md["address"] = v.get("address")
    if v.get("email"): md["email"] = v["email"]
    if v.get("phone"): md["phone"] = v["phone"]

    return {"lines": items, "totals": totals, "metadata": md}

# --------------------------- orchestrator ---------------------------
def process_invoice(file_path: str, db, bill_id: int) -> Dict[str, Any]:
    text = extract_text_from_pdf(file_path)
    parsed = parse_invoice_text(text)

    # lines
    for li in parsed["lines"]:
        db.add(models.BillLine(
            bill_id=bill_id,
            description_raw=li["description_raw"],
            qty=li["qty"],
            unit_price=li["unit_price"],
            line_total=li["line_total"],
            ocr_confidence=li["ocr_confidence"],
            **({"uom": li.get("uom")} if hasattr(models.BillLine, "uom") else {}),
            **({"hsn": li.get("hsn")} if hasattr(models.BillLine, "hsn") else {}),
        ))

    bill = db.get(models.Bill, bill_id)

    totals = parsed["totals"]
    if totals.get("grand_total") is not None:
        bill.total = totals["grand_total"]

    md = parsed["metadata"] or {}
    if md.get("invoice_no"):
        bill.bill_no = md["invoice_no"]
    if md.get("bill_date"):
        try:
            bill.bill_date = datetime.fromisoformat(md["bill_date"]).date()
        except Exception:
            pass

    # ✅ SAFE VENDOR ATTACH (no unique-name crashes)
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

    bill.party_name = md.get("vendor_name", bill.party_name)
    bill.status = "PROCESSED"
    db.commit()

    return {
        "bill_id": bill_id,
        "status": "PROCESSED",
        "lines_saved": len(parsed["lines"]),
        "totals": totals,
        "metadata": md,
    }

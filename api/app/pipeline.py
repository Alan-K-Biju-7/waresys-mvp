from typing import List, Dict, Any
import pdfplumber, pytesseract
from pdf2image import convert_from_path
from PIL import Image
from .parsing import parse_kv_fields_from_zone, parse_line_items_from_tokens

def detect_pdf_mode(file_path: str) -> str:
    try:
        with pdfplumber.open(file_path) as pdf:
            page = pdf.pages[0]
            text = page.extract_text() or ""
            return "text" if len(text.strip()) > 50 else "image"
    except Exception:
        return "image"

def ocr_page(pil: Image.Image) -> str:
    return pytesseract.image_to_string(pil, config="--oem 1 --psm 6")

def extract_tokens_with_positions(file_path: str) -> Dict[str, Any]:
    tokens = []
    zones = {"header": "", "body": "", "footer": ""}
    with pdfplumber.open(file_path) as pdf:
        for p in pdf.pages:
            h = p.height
            words = p.extract_words() or []
            for w in words:
                y = w["top"]
                if y < h * 0.25:
                    zones["header"] += " " + w["text"]
                elif y > h * 0.75:
                    zones["footer"] += " " + w["text"]
                else:
                    zones["body"] += " " + w["text"]
                tokens.append(w["text"])
    return {"tokens": tokens, "zones": zones}

def extract_tokens_scanned_pdf(file_path: str) -> Dict[str, Any]:
    tokens = []
    pages = convert_from_path(file_path, dpi=300)
    for pil in pages:
        txt = ocr_page(pil)
        tokens.extend(txt.split())
    return {"tokens": tokens, "zones": {"body": " ".join(tokens)}}

def run_ocr_pipeline(file_path: str) -> Dict[str, Any]:
    mode = detect_pdf_mode(file_path)
    return extract_tokens_with_positions(file_path) if mode == "text" else extract_tokens_scanned_pdf(file_path)

def parse_invoice(file_path: str, db_session, products_cache: List[Dict[str, Any]]) -> Dict[str, Any]:
    data = run_ocr_pipeline(file_path)
    tokens = data["tokens"]
    zones = data["zones"]

    # Extract fields from header/footer zones
    header_fields = parse_kv_fields_from_zone(zones.get("header", ""))
    footer_fields = parse_kv_fields_from_zone(zones.get("footer", ""))

    # Merge results with priority: header > footer
    kv = {**footer_fields, **header_fields}
    kv["party_name"] = zones.get("header", "").split("Invoice")[0].strip()[:64] or None

    # Parse lines from body
    lines = parse_line_items_from_tokens(tokens)

    # Manual review trigger
    critical_fields = [kv.get("bill_no"), kv.get("bill_date"), kv.get("total")]
    avg_conf = sum([l["ocr_confidence"] for l in lines]) / len(lines) if lines else 0
    needs_review = (not all(critical_fields)) or avg_conf < 0.75

    return {"kv": kv, "lines": lines, "needs_review": needs_review}

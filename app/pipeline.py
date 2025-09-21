from typing import List, Dict, Any
import pdfplumber, pytesseract
from pdf2image import convert_from_path
from PIL import Image,ImageOps
from .parsing import parse_kv_fields_from_zone, parse_line_items_from_tokens
from rapidfuzz import process
from pdf2image import convert_from_path
import pytesseract

def correct_sku(sku: str, known_skus: list[str]) -> str:
    if not sku:
        return sku
    match, score, _ = process.extractOne(sku, known_skus)
    return match if score >= 90 else sku

def extract_text_from_pdf(file_path: str) -> str:
    """OCR the entire PDF into plain text with line breaks."""
    pages = convert_from_path(file_path, dpi=200)
    text_blocks = [pytesseract.image_to_string(page) for page in pages]
    return "\n".join(text_blocks)

def detect_pdf_mode(file_path: str) -> str:
    try:
        with pdfplumber.open(file_path) as pdf:
            page = pdf.pages[0]
            text = page.extract_text() or ""
            return "text" if len(text.strip()) > 50 else "image"
    except Exception:
        return "image"

def ocr_page(pil: Image.Image) -> str:
    # Preprocess image
    pil = pil.convert("L")  # grayscale
    # Apply thresholding
    pil = pil.point(lambda x: 0 if x < 180 else 255, '1')

    # OCR with tuned config
    config = "--oem 3 --psm 4 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-./"
    return pytesseract.image_to_string(pil, config=config)

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
    zones = {"body": ""}

    pages = convert_from_path(file_path, dpi=300)
    for pil in pages:
        txt = ocr_page(pil)  # uses improved OCR above
        lines = txt.splitlines()
        for line in lines:
            clean_line = line.strip()
            if clean_line:
                tokens.extend(clean_line.split())
                zones["body"] += " " + clean_line

    return {"tokens": tokens, "zones": zones}


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

    raw_text = extract_text_from_pdf(file_path)
    lines = parse_line_items_from_tokens(raw_text.splitlines())

    
    # ✅ Correct SKUs if product catalog is known
    known_skus = [p["sku"] for p in products_cache] if products_cache else []
    # Inside parse_invoice()
    if known_skus:
        for l in lines:
            parts = l["description_raw"].split()
            if parts:
                fixed = correct_sku(parts[0], known_skus)
                l["sku"] = fixed   # ✅ update sku field directly
                l["description_raw"] = fixed + " " + " ".join(parts[1:])


    # Manual review trigger
    critical_fields = [kv.get("bill_no"), kv.get("bill_date"), kv.get("total")]
    avg_conf = sum([l["ocr_confidence"] for l in lines]) / len(lines) if lines else 0
    needs_review = (not all(critical_fields)) or avg_conf < 0.75
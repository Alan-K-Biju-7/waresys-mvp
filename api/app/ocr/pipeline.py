from typing import List, Dict, Any
import pdfplumber, pytesseract
from pdf2image import convert_from_path
from PIL import Image
from .parsing import parse_kv_fields, parse_line_items_from_tokens
from .matching import match_line_to_catalog

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

def extract_tokens_text_pdf(file_path: str) -> Dict[str, Any]:
    tokens = []
    with pdfplumber.open(file_path) as pdf:
        for p in pdf.pages:
            words = p.extract_words() or []
            tokens.extend([w.get("text","") for w in words])
    return {"tokens": tokens}

def extract_tokens_scanned_pdf(file_path: str) -> Dict[str, Any]:
    tokens = []
    pages = convert_from_path(file_path, dpi=300)
    for pil in pages:
        txt = ocr_page(pil)
        tokens.extend(txt.split())
    return {"tokens": tokens}

def run_ocr_pipeline(file_path: str) -> Dict[str, Any]:
    mode = detect_pdf_mode(file_path)
    return extract_tokens_text_pdf(file_path) if mode == "text" else extract_tokens_scanned_pdf(file_path)

def parse_invoice(file_path: str, db_session, products_cache: List[Dict[str, Any]]) -> Dict[str, Any]:
    data = run_ocr_pipeline(file_path)
    tokens: List[str] = data["tokens"]
    kv = parse_kv_fields(tokens)
    lines = parse_line_items_from_tokens(tokens)
    parsed_lines = []
    for ln in lines:
        m = match_line_to_catalog(ln, db_session, products_cache)
        parsed_lines.append(m)
    return {"kv": kv, "lines": parsed_lines}

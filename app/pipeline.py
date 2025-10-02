import logging
import pytesseract
from pdf2image import convert_from_path
from . import parsing

logger = logging.getLogger(__name__)

def ocr_pdf(file_path: str) -> str:
    try:
        images = convert_from_path(file_path, dpi=300)
    except Exception as e:
        logger.error(f"PDF conversion failed: {e}")
        return ""
    blocks = []
    for i, img in enumerate(images):
        try:
            text = pytesseract.image_to_string(img, config="--psm 6")
            blocks.append(text)
        except Exception as e:
            logger.warning(f"OCR failed on page {i}: {e}")
    return "\n".join(blocks)

def parse_invoice(file_path: str, db=None, products_cache=None) -> dict:
    """
    Legacy Bill pipeline: OCR + generic header/lines (still useful for simple bills).
    Returns shape compatible with tasks.process_invoice().
    """
    raw_text = ocr_pdf(file_path)
    if not raw_text.strip():
        return {"kv": {}, "lines": [], "needs_review": True}
    header = parsing.parse_header(raw_text)
    lines = parsing.deduplicate_lines(parsing.parse_lines(raw_text))
    needs_review = any(l.get("ocr_confidence", 1.0) < 0.9 for l in lines)
    return {"kv": header, "lines": lines, "needs_review": needs_review}

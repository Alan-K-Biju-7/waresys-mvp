import pytesseract
from pdf2image import convert_from_path
import logging
from . import parsing

logger = logging.getLogger(__name__)

def ocr_pdf(file_path: str) -> str:
    """Convert PDF → images → OCR text."""
    try:
        images = convert_from_path(file_path, dpi=300)
    except Exception as e:
        logger.error(f"PDF conversion failed: {e}")
        return ""

    full_text = []
    for i, img in enumerate(images):
        try:
            # --psm 6 treats the page as a uniform block of text (good for rows)
            text = pytesseract.image_to_string(img, config="--psm 6")
            full_text.append(text)
        except Exception as e:
            logger.warning(f"OCR failed on page {i}: {e}")

    return "\n".join(full_text)

def parse_invoice(file_path: str, db=None, products_cache=None) -> dict:
    """
    Full OCR + parsing pipeline.
    db/products_cache kept for backward compatibility with tasks.py.
    """
    raw_text = ocr_pdf(file_path)
    logger.debug(f"OCR chars: {len(raw_text)}. Preview:\n{raw_text[:400]}")

    if not raw_text.strip():
        logger.warning(f"OCR returned empty text for {file_path}")
        return {"kv": {}, "lines": [], "needs_review": True}

    header = parsing.parse_header(raw_text)
    lines = parsing.parse_lines(raw_text)  # uses multi-pattern + fallback
    lines = parsing.deduplicate_lines(lines)

    if not lines:
        logger.warning(f"No lines parsed from {file_path}")
        return {"kv": header, "lines": [], "needs_review": True}

    needs_review = any(l.get("ocr_confidence", 1.0) < 0.9 for l in lines)
    return {"kv": header, "lines": lines, "needs_review": needs_review}

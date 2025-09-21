from typing import Dict, Any, List
from rapidfuzz import fuzz
from sqlalchemy.orm import Session
from . import crud
import re

def normalize_sku(sku: str) -> str:
    """Normalize OCR’d SKUs (e.g., fix common digit/letter confusions)."""
    if not sku:
        return ""
    sku = sku.upper()
    # Replace common OCR mistakes
    sku = sku.replace("O", "0")   # letter O → zero
    sku = sku.replace("I", "1")   # letter I → one
    return sku

def match_line_to_catalog(line: Dict[str, Any], db: Session, products_cache: List[Dict[str, Any]]) -> Dict[str, Any]:
    desc = (line.get("description_raw") or "").lower()
    qty = float(line.get("qty") or 0)
    unit_price = line.get("unit_price")
    sku = line.get("sku")

    resolved_id = None
    score = 0.0

    # 1. Try explicit OCR SKU first
    if sku:
        norm_sku = normalize_sku(sku)
        p = crud.get_product_by_sku(db, norm_sku)
        if p:
            resolved_id = p.id
            score = 1.0

    # 2. Try SKU-like tokens in description
    if not resolved_id:
        for tok in desc.split():
            if len(tok) >= 4 and tok.isalnum():
                norm_tok = normalize_sku(tok)
                p = crud.get_product_by_sku(db, norm_tok)
                if p:
                    resolved_id = p.id
                    score = 0.9
                    break

    # 3. Fuzzy match by product name
    if not resolved_id:
        best = None
        for p in products_cache:
            s = fuzz.WRatio(desc, p["name"].lower()) / 100.0
            if not best or s > best[0]:
                best = (s, p["id"])
        if best and best[0] >= 0.75:
            resolved_id = best[1]
            score = best[0]

    # Always return enriched line
    return {
        **line,  # keep original OCR fields like sku
        "candidate_product_ids": [resolved_id] if resolved_id else [],
        "match_score": float(score),
        "ocr_confidence": 0.95 if score >= 0.9 else (0.75 if score >= 0.7 else 0.5),
        "resolved_product_id": resolved_id,
    }

from typing import Dict, Any, List
from rapidfuzz import fuzz
from sqlalchemy.orm import Session
from . import crud

def match_line_to_catalog(line: Dict[str, Any], db: Session, products_cache: List[Dict[str, Any]]) -> Dict[str, Any]:
    desc = (line.get("description_raw") or "").lower()
    qty = float(line.get("qty") or 0)
    unit_price = line.get("unit_price")

    # Try exact SKU tokens
    for tok in desc.split():
        if len(tok) >= 4 and tok.isalnum():
            p = crud.get_product_by_sku(db, tok.upper())
            if p:
                return {"description_raw": line["description_raw"], "qty": qty, "unit_price": unit_price,
                        "line_total": line.get("line_total"), "candidate_product_ids": [p.id],
                        "match_score": 1.0, "ocr_confidence": 0.9, "resolved_product_id": p.id}

    # Fuzzy name match
    best = None
    for p in products_cache:
        score = fuzz.WRatio(desc, p["name"].lower())/100.0
        if not best or score > best[0]:
            best = (score, p["id"])
    resolved = best[1] if best and best[0] >= 0.75 else None
    return {"description_raw": line["description_raw"], "qty": qty, "unit_price": unit_price,
            "line_total": line.get("line_total"), "candidate_product_ids": [best[1]] if best else [],
            "match_score": float(best[0]) if best else 0.0, "ocr_confidence": 0.75 if resolved else 0.6,
            "resolved_product_id": resolved}

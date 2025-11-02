def _clean_line(raw: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], str | None]:
    desc = (raw.get("description_raw") or "").strip()
    if not desc or BLOCKLIST.search(desc):
        return None, "blocked_by_text"

    qty = _fnum(raw.get("qty"))
    unit = _fnum(raw.get("unit_price"))
    total = _fnum(raw.get("line_total") or qty * unit)

    if qty <= 0 or unit < 0 or total < 0:
        return None, "non_positive_numbers"
    if qty > MAX_QTY or unit > MAX_UNIT_PRICE or total > MAX_LINE_TOTAL:
        return None, "out_of_range"

    cleaned = dict(
        description_raw=desc[:512],
        qty=round(qty, 3),
        unit_price=round(unit, 2),
        line_total=round(total, 2),
        ocr_confidence=_fnum(raw.get("ocr_confidence"), 0.0),
    )
    return cleaned, None

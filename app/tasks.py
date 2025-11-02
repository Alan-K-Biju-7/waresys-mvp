def _run_parsing_adapter(file_path: str, db: Session) -> Optional[Dict[str, Any]]:
    """
    Returns a dict like:
      { "kv": {...}, "lines": [...], "needs_review": bool, "vendor": {...} }
    using legacy or OCR text parser.
    """

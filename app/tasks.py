    if legacy_parse_invoice:
        try:
            out = legacy_parse_invoice(
                file_path,
                db,
                products_cache=[
                    {"id": p.id, "sku": getattr(p, "sku", None), "name": p.name}
                    for p in db.query(models.Product).all()
                ],
            )
            if out:
                out.setdefault("vendor", None)
                return out
        except Exception:
            logger.exception("[adapter] legacy_parse_invoice failed; trying OCR pipeline")

    if extract_text_from_pdf and parse_invoice_text:
        text = extract_text_from_pdf(file_path)
        parsed2 = parse_invoice_text(text) or {}

        md = parsed2.get("metadata") or {}
        totals = parsed2.get("totals") or {}
        kv = {
            "bill_no": md.get("invoice_no"),
            "bill_date": md.get("bill_date"),
            "party_name": md.get("party_name") or md.get("vendor_name"),
            "total": totals.get("grand_total"),
        }
        vendor = {
            "name": md.get("vendor_name"),
            "gst_number": md.get("gst_number"),
            "address": md.get("address"),
            "contact": md.get("phone") or md.get("contact"),
            "email": md.get("email"),
        }
        lines = parsed2.get("lines") or []
        needs_review = not bool(lines)
        return {"kv": kv, "lines": lines, "needs_review": needs_review, "vendor": vendor}

    return None

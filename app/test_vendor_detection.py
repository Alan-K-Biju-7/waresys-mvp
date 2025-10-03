from app.vendor_detection import detect_vendor_from_lines

def test_detects_vendor_near_gstin_and_ignores_buyer_block():
    lines = [
        "TAX INVOICE",
        "MERCHANTS ASSOCIATION BLDGS",
        "NEAR SOUTH INDIAN BANK, KORATTY, THRISSUR, KERALA - 680308",
        "GSTIN : 32EHSPK6796N1Z8",
        "Phone: +91-9496865950, Email: a2zbuildwares@gmail.com",
        "-----------------------------------------",
        "Bill To : KORATTY JOY MYNATTY",
        "Address: Kochi, Kerala 682030",
        "GSTIN: 32ABCDE1234F1Z5",
        "Place of Supply : Kerala (32)",
    ]
    out = detect_vendor_from_lines(lines)
    assert out["gstin"] == "32EHSPK6796N1Z8"
    assert out["name"] == "MERCHANTS ASSOCIATION BLDGS"
    assert out["pos_state_code"] in ("32", None)  # may come from POS or GSTIN prefix
    assert out["needs_review"] is False or out["score"] >= 60

def test_falls_back_to_cues_when_no_gstin():
    lines = [
        "Tax Invoice From",
        "Acme Tiles & Sanitary Pvt Ltd",
        "Regd. Office: 12 MG Road, Bengaluru - 560001",
        "Bill To: Some Buyer",
        "Ship To: Another Address",
        "POS: Karnataka 29",
    ]
    out = detect_vendor_from_lines(lines)
    assert out["name"] in ("Acme Tiles & Sanitary Pvt Ltd", "Tax Invoice From")
    assert out["gstin"] is None
    assert out["needs_review"] is True

def test_avoids_picking_customer_block():
    lines = [
        "Seller: Alpha Buildwares LLP",
        "State Code: 32",
        "GSTIN: 32AABCA1234A1ZV",
        "---------------------",
        "Buyer: Beta Constructions",
        "GSTIN: 27BBBCC2345B1Z2",
    ]
    out = detect_vendor_from_lines(lines)
    assert out["gstin"].startswith("32")
    assert "Alpha" in (out["name"] or "")

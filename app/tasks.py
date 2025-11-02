BLOCKLIST = re.compile(
    r"(state\\s*name|gst|sgst|cgst|igst|code\\b|pan\\b|cin\\b|"
    r"invoice\\s*no|invoice\\s*date|bill\\s*no|po\\s*no|"
    r"address|contact|bank|ifsc|subtotal|sub\\s*total|"
    r"round\\s*off|grand\\s*total|total\\b)",
    re.IGNORECASE,
)

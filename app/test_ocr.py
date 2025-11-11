from pdf2image import convert_from_path
import pytesseract
import sys, os

if len(sys.argv) < 2:
    print("⚠️ Usage: python test_ocr.py /app/uploads/<file.pdf>")
    sys.exit(1)

pdf_file = sys.argv[1]

if not os.path.exists(pdf_file):
    print(f"⚠️ File not found: {pdf_file}")
    sys.exit(1)

pages = convert_from_path(pdf_file, dpi=150)

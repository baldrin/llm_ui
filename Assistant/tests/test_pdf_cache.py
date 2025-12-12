# test_pdf.py
from utils.content.pdf_handler import pdf_handler

# You'll need a small test PDF
with open('test.pdf', 'rb') as f:
    pdf_bytes = f.read()

# First call - should calculate
metadata = pdf_handler.estimate_pdf_metadata(pdf_bytes)
print("First call:", metadata)

# Second call - should hit cache
metadata = pdf_handler.estimate_pdf_metadata(pdf_bytes)
print("Second call (cached):", metadata)

# Test encoding
encoded = pdf_handler.encode_pdf(pdf_bytes)
print(f"Encoded length: {len(encoded)}")

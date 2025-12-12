"""
Integration test for PDF handling across all components.
Tests: PDFHandler → TokenCalculator → ContextManager
"""

from utils.content.pdf_handler import pdf_handler
from utils.content.token_calculator import token_calculator
from utils.chat.context_manager import context_manager

print("=" * 60)
print("PDF INTEGRATION TEST")
print("=" * 60)

# Load test PDF
with open('test.pdf', 'rb') as f:
    pdf_bytes = f.read()

print(f"\nTest PDF size: {len(pdf_bytes)} bytes ({len(pdf_bytes)/1024:.2f} KB)")

# ============================================================
# TEST 1: PDFHandler metadata calculation
# ============================================================
print("\n" + "=" * 60)
print("TEST 1: PDFHandler.estimate_pdf_metadata()")
print("=" * 60)

metadata1 = pdf_handler.estimate_pdf_metadata(pdf_bytes)
print("First call (should calculate):")
print(f"  - Payload size: {metadata1['payload_size_bytes']} bytes ({metadata1['payload_size_bytes']/1024:.2f} KB)")
print(f"  - File size: {metadata1['file_size_bytes']} bytes ({metadata1['file_size_bytes']/1024:.2f} KB)")
print(f"  - Pages: {metadata1['pages']}")
print(f"  - Tokens: {metadata1['tokens']}")
print(f"  - Ratio: {metadata1['payload_size_bytes'] / metadata1['file_size_bytes']:.3f}x")

metadata2 = pdf_handler.estimate_pdf_metadata(pdf_bytes)
print("\nSecond call (should hit cache):")
print(f"  - Same result: {metadata1 == metadata2}")

# ============================================================
# TEST 2: TokenCalculator with PDF
# ============================================================
print("\n" + "=" * 60)
print("TEST 2: TokenCalculator.estimate_message_tokens()")
print("=" * 60)

message_text = "Please analyze this PDF document."
pdfs = [{'bytes': pdf_bytes}]

total_tokens = token_calculator.estimate_message_tokens(
    text=message_text,
    pdfs=pdfs
)

text_tokens = token_calculator.estimate_text_tokens(message_text)
pdf_tokens = metadata1['tokens']

print(f"Message: '{message_text}'")
print(f"  - Text tokens: {text_tokens}")
print(f"  - PDF tokens: {pdf_tokens}")
print(f"  - Total tokens: {total_tokens}")
print(f"  - Match: {total_tokens == text_tokens + pdf_tokens}")

# ============================================================
# TEST 3: ContextManager request size estimation
# ============================================================
print("\n" + "=" * 60)
print("TEST 3: ContextManager.estimate_request_size()")
print("=" * 60)

messages = []  # Empty conversation
attachments = {
    'pdfs': [{'bytes': pdf_bytes}]
}

request_size = context_manager.estimate_request_size(
    messages=messages,
    new_message=message_text,
    attachments=attachments
)

print("Request size estimation:")
print(f"  - Total size: {request_size} bytes ({request_size/1024:.2f} KB)")
print(f"  - Expected: ~{metadata1['payload_size_bytes'] + len(message_text)} bytes")
print(f"  - Within range: {abs(request_size - metadata1['payload_size_bytes']) < 1000}")

# ============================================================
# TEST 4: ContextManager validation (can send?)
# ============================================================
print("\n" + "=" * 60)
print("TEST 4: ContextManager.validate_can_send()")
print("=" * 60)

validation = context_manager.validate_can_send(
    messages=messages,
    new_message=message_text,
    attachments=attachments
)

print("Validation result:")
print(f"  - Can send: {validation.can_send}")
print(f"  - Error message: {validation.error_message}")
print(f"  - Details: {validation.details}")

# ============================================================
# TEST 5: Multiple PDFs (cache efficiency)
# ============================================================
print("\n" + "=" * 60)
print("TEST 5: Multiple PDFs with same content (cache test)")
print("=" * 60)

# Simulate uploading the same PDF 3 times
pdfs_multiple = [
    {'bytes': pdf_bytes},
    {'bytes': pdf_bytes},
    {'bytes': pdf_bytes}
]

total_tokens_multi = token_calculator.estimate_message_tokens(
    text="Analyze these documents.",
    pdfs=pdfs_multiple
)

expected_tokens = token_calculator.estimate_text_tokens("Analyze these documents.") + (metadata1['tokens'] * 3)

print("3 identical PDFs:")
print(f"  - Total tokens: {total_tokens_multi}")
print(f"  - Expected: {expected_tokens}")
print(f"  - Match: {total_tokens_multi == expected_tokens}")
print("  - Cache hits: Should see 3 cache hits in logs above")

# ============================================================
# TEST 6: PDF encoding
# ============================================================
print("\n" + "=" * 60)
print("TEST 6: PDFHandler.encode_pdf()")
print("=" * 60)

encoded = pdf_handler.encode_pdf(pdf_bytes)
print("Encoded PDF:")
print(f"  - Length: {len(encoded)} bytes")
print(f"  - Matches metadata: {len(encoded) == metadata1['payload_size_bytes']}")
print(f"  - First 50 chars: {encoded[:50]}...")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)

all_tests_passed = (
    metadata1 == metadata2 and  # Cache works
    total_tokens == text_tokens + pdf_tokens and  # Token calc correct
    abs(request_size - metadata1['payload_size_bytes']) < 1000 and  # Size calc correct
    validation.can_send and  # Validation passes
    total_tokens_multi == expected_tokens and  # Multiple PDFs work
    len(encoded) == metadata1['payload_size_bytes']  # Encoding correct
)

if all_tests_passed:
    print("✅ ALL TESTS PASSED!")
else:
    print("❌ SOME TESTS FAILED - Check output above")

print("=" * 60)

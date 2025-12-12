from PIL import Image
from utils.content.image_encoder import estimate_image_size

print("Testing updated image cache...")

# Create test image
img = Image.new('RGB', (100, 100), color='red')

# First call
print("\nFirst call (should calculate):")
result1 = estimate_image_size(img)
print(f"  Result: {result1}")

# Second call
print("\nSecond call (should hit cache):")
result2 = estimate_image_size(img)
print(f"  Result: {result2}")

# Verify
print(f"\nResults match: {result1 == result2}")
print(f"No 'cached_at' in result: {'cached_at' not in result1}")

if result1 == result2 and 'cached_at' not in result1:
    print("\n✅ Image cache update successful!")
else:
    print("\n❌ Something went wrong")

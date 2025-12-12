# In a Python console or test script
from PIL import Image
from utils.content.image_encoder import estimate_image_size

# Create a small test image
img = Image.new('RGB', (100, 100), color='red')

# Get the size info
result = estimate_image_size(img)

print(result)
# Should show: {'payload_size_bytes': ~X, 'file_size_bytes': ~Y, 'format': 'JPEG', 'resized': False}
# payload_size_bytes should be about 1.33x file_size_bytes

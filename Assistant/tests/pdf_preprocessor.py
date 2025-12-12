#!/usr/bin/env python3
"""
PDF Fax Preprocessor
Cleans and enhances poor quality fax images before OCR/LLM processing.
"""

import argparse
import sys
import cv2
import numpy as np
import fitz  # PyMuPDF

def pdf_page_to_image(pdf_path, page_num):
    """Convert a PDF page to a numpy array image."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]

    # Render page to image at 300 DPI
    mat = fitz.Matrix(300/72, 300/72)
    pix = page.get_pixmap(matrix=mat)

    # Convert to numpy array
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

    # Convert to grayscale if needed
    if len(img.shape) == 3 and img.shape[2] > 1:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    doc.close()
    return img

def image_to_pdf(images, output_path):
    """Convert list of images to PDF."""
    if not images:
        return

    # Create PDF document
    doc = fitz.open()

    for img in images:
        # Convert numpy array to bytes
        if len(img.shape) == 2:  # Grayscale
            img_rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        else:
            img_rgb = img

        # Create a new page with image dimensions
        height, width = img_rgb.shape[:2]
        page = doc.new_page(width=width, height=height)

        # Convert to PNG bytes
        success, buffer = cv2.imencode('.png', img_rgb)
        if not success:
            print("Warning: Failed to encode image", file=sys.stderr)
            continue

        img_bytes = buffer.tobytes()

        # Insert image
        page.insert_image(page.rect, stream=img_bytes)

    # Save PDF
    doc.save(output_path)
    doc.close()

def denoise_image(image, method='bilateral'):
    """
    Remove noise from image while preserving edges.

    Methods:
    - bilateral: Good for preserving edges while removing noise
    - gaussian: Simple blur, faster but less edge-preserving
    - median: Good for salt-and-pepper noise
    - nlmeans: Best quality but slowest
    """
    if method == 'bilateral':
        # Bilateral filter preserves edges while smoothing
        return cv2.bilateralFilter(image, 9, 75, 75)

    elif method == 'gaussian':
        # Simple Gaussian blur
        return cv2.GaussianBlur(image, (5, 5), 0)

    elif method == 'median':
        # Median filter - good for salt-and-pepper noise
        return cv2.medianBlur(image, 5)

    elif method == 'nlmeans':
        # Non-local means - highest quality but slowest
        return cv2.fastNlMeansDenoising(image, None, 10, 7, 21)

    else:
        return image

def enhance_contrast(image, method='clahe'):
    """
    Enhance image contrast.

    Methods:
    - clahe: Adaptive histogram equalization (best for documents)
    - histogram: Global histogram equalization
    - normalize: Simple normalization
    """
    if method == 'clahe':
        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(image)

    elif method == 'histogram':
        # Global histogram equalization
        return cv2.equalizeHist(image)

    elif method == 'normalize':
        # Normalize to full range
        return cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX)

    else:
        return image

def binarize_image(image, method='adaptive'):
    """
    Convert to pure black and white.

    Methods:
    - adaptive: Adaptive thresholding (best for varying lighting)
    - otsu: Otsu's method (good for bimodal histograms)
    - simple: Simple global threshold
    """
    if method == 'adaptive':
        # Adaptive thresholding - handles varying background
        return cv2.adaptiveThreshold(
            image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

    elif method == 'otsu':
        # Otsu's method - automatically finds optimal threshold
        _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    elif method == 'simple':
        # Simple threshold at 127
        _, binary = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
        return binary

    else:
        return image

def deskew_image(image):
    """Correct skewed/rotated documents."""
    # Threshold the image
    _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Find all contours
    coords = np.column_stack(np.where(binary > 0))

    if len(coords) < 5:
        return image

    # Calculate rotation angle
    angle = cv2.minAreaRect(coords)[-1]

    # Normalize angle
    if angle < -45:
        angle = 90 + angle
    elif angle > 45:
        angle = angle - 90

    # Only rotate if skew is significant (> 0.5 degrees)
    if abs(angle) < 0.5:
        return image

    # Rotate image
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, 
                             borderMode=cv2.BORDER_REPLICATE)

    return rotated

def sharpen_image(image, strength='medium'):
    """
    Sharpen image to enhance text edges.

    Strength: light, medium, strong
    """
    kernels = {
        'light': np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]]),
        'medium': np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]]),
        'strong': np.array([[-1, -1, -1, -1, -1],
                           [-1, 2, 2, 2, -1],
                           [-1, 2, 8, 2, -1],
                           [-1, 2, 2, 2, -1],
                           [-1, -1, -1, -1, -1]]) / 8.0
    }

    kernel = kernels.get(strength, kernels['medium'])
    return cv2.filter2D(image, -1, kernel)

def remove_borders(image, border_size=20):
    """Remove black borders that sometimes appear on faxes."""
    h, w = image.shape[:2]
    return image[border_size:h-border_size, border_size:w-border_size]

def preprocess_pipeline(image, config):
    """Run full preprocessing pipeline based on config."""
    processed = image.copy()

    print("  Processing steps:", end=" ")

    # Step 1: Remove borders if enabled
    if config['remove_borders']:
        processed = remove_borders(processed, config['border_size'])
        print("borders", end=" ")

    # Step 2: Deskew if enabled
    if config['deskew']:
        processed = deskew_image(processed)
        print("deskew", end=" ")

    # Step 3: Denoise if enabled
    if config['denoise']:
        processed = denoise_image(processed, config['denoise_method'])
        print(f"denoise({config['denoise_method']})", end=" ")

    # Step 4: Enhance contrast if enabled
    if config['enhance_contrast']:
        processed = enhance_contrast(processed, config['contrast_method'])
        print(f"contrast({config['contrast_method']})", end=" ")

    # Step 5: Sharpen if enabled
    if config['sharpen']:
        processed = sharpen_image(processed, config['sharpen_strength'])
        print(f"sharpen({config['sharpen_strength']})", end=" ")

    # Step 6: Binarize if enabled (should be last)
    if config['binarize']:
        processed = binarize_image(processed, config['binarize_method'])
        print(f"binarize({config['binarize_method']})", end=" ")

    print("✓")
    return processed

def main():
    parser = argparse.ArgumentParser(
        description='Preprocess poor quality fax PDFs for better OCR/LLM results.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic cleanup with defaults
  python preprocess_fax.py -i input.pdf -o cleaned.pdf

  # Aggressive cleaning for very poor quality
  python preprocess_fax.py -i input.pdf -o cleaned.pdf --denoise nlmeans --sharpen strong

  # Just deskew and binarize
  python preprocess_fax.py -i input.pdf -o cleaned.pdf --no-denoise --no-contrast

  # Process only first 3 pages
  python preprocess_fax.py -i input.pdf -o cleaned.pdf -n 3
        """
    )

    parser.add_argument('-i', '--input', required=True,
                        help='Input PDF file path')
    parser.add_argument('-o', '--output', required=True,
                        help='Output PDF file path')
    parser.add_argument('-n', '--num-pages', type=int, default=None,
                        help='Number of pages to process (default: all pages)')

    # Processing options
    parser.add_argument('--no-denoise', action='store_true',
                        help='Disable noise removal')
    parser.add_argument('--denoise-method', choices=['bilateral', 'gaussian', 'median', 'nlmeans'],
                        default='bilateral', help='Denoising method (default: bilateral)')

    parser.add_argument('--no-contrast', action='store_true',
                        help='Disable contrast enhancement')
    parser.add_argument('--contrast-method', choices=['clahe', 'histogram', 'normalize'],
                        default='clahe', help='Contrast method (default: clahe)')

    parser.add_argument('--no-binarize', action='store_true',
                        help='Disable binarization (keep grayscale)')
    parser.add_argument('--binarize-method', choices=['adaptive', 'otsu', 'simple'],
                        default='adaptive', help='Binarization method (default: adaptive)')

    parser.add_argument('--no-deskew', action='store_true',
                        help='Disable deskewing')

    parser.add_argument('--no-sharpen', action='store_true',
                        help='Disable sharpening')
    parser.add_argument('--sharpen-strength', choices=['light', 'medium', 'strong'],
                        default='medium', help='Sharpening strength (default: medium)')

    parser.add_argument('--no-borders', action='store_true',
                        help='Disable border removal')
    parser.add_argument('--border-size', type=int, default=20,
                        help='Border size to remove in pixels (default: 20)')

    args = parser.parse_args()

    # Build configuration
    config = {
        'denoise': not args.no_denoise,
        'denoise_method': args.denoise_method,
        'enhance_contrast': not args.no_contrast,
        'contrast_method': args.contrast_method,
        'binarize': not args.no_binarize,
        'binarize_method': args.binarize_method,
        'deskew': not args.no_deskew,
        'sharpen': not args.no_sharpen,
        'sharpen_strength': args.sharpen_strength,
        'remove_borders': not args.no_borders,
        'border_size': args.border_size,
    }

    # Open PDF and get page count
    try:
        doc = fitz.open(args.input)
        total_pages = len(doc)
        doc.close()
    except Exception as e:
        print(f"Error opening PDF: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine pages to process
    pages_to_process = args.num_pages if args.num_pages else total_pages
    pages_to_process = min(pages_to_process, total_pages)

    print(f"\nPreprocessing PDF: {args.input}")
    print(f"Total pages: {total_pages}")
    print(f"Processing: {pages_to_process} page(s)")
    print(f"Output: {args.output}")
    print("\nEnabled processing steps:")
    for key, value in config.items():
        if isinstance(value, bool) and value:
            print(f"  ✓ {key.replace('_', ' ').title()}")
    print()

    # Process each page
    processed_images = []

    for page_num in range(pages_to_process):
        print(f"Processing page {page_num + 1}/{pages_to_process}...", end=" ")

        try:
            # Convert page to image
            image = pdf_page_to_image(args.input, page_num)

            # Run preprocessing pipeline
            processed = preprocess_pipeline(image, config)
            processed_images.append(processed)

        except Exception as e:
            print(f"\n  Error processing page {page_num + 1}: {e}", file=sys.stderr)
            # Add original image if processing fails
            processed_images.append(image)
            continue

    # Save processed images as PDF
    print(f"\nSaving processed PDF to {args.output}...")
    try:
        image_to_pdf(processed_images, args.output)
        print("✓ Processing complete!\n")
    except Exception as e:
        print(f"Error saving PDF: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
PDF Fax Quality Analyzer
Analyzes PDF pages for image quality using multiple metrics.
"""

import argparse
import sys
import cv2
import numpy as np
import fitz  # PyMuPDF
import pytesseract
from collections import defaultdict

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

def laplacian_variance(image):
    """
    Measure image sharpness using Laplacian variance.
    Higher values = sharper image.

    Score Range: 0-1000+ (typical good fax: >100, poor: <50)
    """
    laplacian = cv2.Laplacian(image, cv2.CV_64F)
    variance = laplacian.var()
    return variance

def tesseract_confidence(image):
    """
    Get average OCR confidence score from Tesseract.
    Higher values = better text recognition.

    Score Range: 0-100 (good: >70, marginal: 50-70, poor: <50)
    """
    try:
        # Get detailed OCR data
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

        # Filter out empty confidences (-1 values)
        confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]

        if not confidences:
            return 0.0

        avg_confidence = sum(confidences) / len(confidences)
        return avg_confidence
    except Exception as e:
        print(f"Warning: Tesseract analysis failed: {e}", file=sys.stderr)
        return 0.0

def contrast_ratio(image):
    """
    Calculate RMS contrast of the image.
    Higher values = better contrast.

    Score Range: 0-100+ (good: >30, marginal: 15-30, poor: <15)
    """
    # Calculate standard deviation as measure of contrast
    contrast = image.std()
    return contrast

def edge_density(image):
    """
    Measure density of edges in the image.
    Higher values = more defined text/content.

    Score Range: 0-100 (good: >5, marginal: 2-5, poor: <2)
    """
    # Apply Canny edge detection
    edges = cv2.Canny(image, 50, 150)

    # Calculate percentage of edge pixels
    edge_pixels = np.count_nonzero(edges)
    total_pixels = edges.size
    density = (edge_pixels / total_pixels) * 100

    return density

def signal_to_noise_ratio(image):
    """
    Estimate signal-to-noise ratio.
    Higher values = cleaner image with less noise.

    Score Range: 0-50+ (good: >15, marginal: 8-15, poor: <8)
    """
    # Calculate mean and standard deviation
    mean = np.mean(image)
    std = np.std(image)

    if std == 0:
        return 0.0

    snr = mean / std
    return snr

def text_area_ratio(image):
    """
    Estimate the ratio of text/content area to background.
    Higher values = more content present.

    Score Range: 0-100 (good: >10, marginal: 5-10, poor: <5)
    """
    # Apply adaptive thresholding to separate text from background
    binary = cv2.adaptiveThreshold(
        image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY_INV, 11, 2
    )

    # Calculate percentage of "text" pixels
    text_pixels = np.count_nonzero(binary)
    total_pixels = binary.size
    ratio = (text_pixels / total_pixels) * 100

    return ratio

def skew_angle_detection(image):
    """
    Detect the skew angle of the document.
    Lower absolute values = better aligned document.

    Score Range: 0-45 degrees (good: <2°, marginal: 2-5°, poor: >5°)
    Returns the absolute skew angle.
    """
    # Threshold the image to binary
    _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Find all contours
    coords = np.column_stack(np.where(binary > 0))

    # Calculate the minimum area rectangle that contains all text
    if len(coords) < 5:  # Need at least 5 points for minAreaRect
        return 0.0

    angle = cv2.minAreaRect(coords)[-1]

    # Normalize angle to -45 to 45 range
    if angle < -45:
        angle = 90 + angle
    elif angle > 45:
        angle = angle - 90

    # Return absolute value (we care about magnitude, not direction)
    return abs(angle)

def analyze_page(image, tests):
    """Run enabled tests on a page image."""
    results = {}

    if tests['laplacian']:
        results['Laplacian Variance'] = laplacian_variance(image)

    if tests['tesseract']:
        results['Tesseract Confidence'] = tesseract_confidence(image)

    if tests['contrast']:
        results['Contrast Ratio'] = contrast_ratio(image)

    if tests['edge']:
        results['Edge Density'] = edge_density(image)

    if tests['snr']:
        results['Signal-to-Noise Ratio'] = signal_to_noise_ratio(image)

    if tests['text']:
        results['Text Area Ratio'] = text_area_ratio(image)

    if tests['skew']:
        results['Skew Angle'] = skew_angle_detection(image)

    return results

def get_quality_rating(metric_name, score):
    """Determine quality rating based on metric and score."""
    thresholds = {
        'Laplacian Variance': {'good': 100, 'marginal': 50},
        'Tesseract Confidence': {'good': 70, 'marginal': 50},
        'Contrast Ratio': {'good': 30, 'marginal': 15},
        'Edge Density': {'good': 5, 'marginal': 2},
        'Signal-to-Noise Ratio': {'good': 15, 'marginal': 8},
        'Text Area Ratio': {'good': 10, 'marginal': 5},
        'Skew Angle': {'good': 2, 'marginal': 5, 'inverted': True},  # Lower is better
    }

    if metric_name not in thresholds:
        return 'UNKNOWN'

    t = thresholds[metric_name]
    inverted = t.get('inverted', False)

    if inverted:
        # For metrics where lower is better (like skew angle)
        if score <= t['good']:
            return 'GOOD'
        elif score <= t['marginal']:
            return 'MARGINAL'
        else:
            return 'POOR'
    else:
        # For metrics where higher is better
        if score >= t['good']:
            return 'GOOD'
        elif score >= t['marginal']:
            return 'MARGINAL'
        else:
            return 'POOR'

def calculate_composite_scores(all_results):
    """
    Calculate composite scores across all pages.
    Uses multiple aggregation methods to provide comprehensive view.
    """
    if not all_results:
        return {}

    composite = {}

    # Group scores by metric
    metric_scores = defaultdict(list)
    for page_results in all_results:
        for metric, score in page_results.items():
            metric_scores[metric].append(score)

    # Calculate statistics for each metric
    for metric, scores in metric_scores.items():
        scores_array = np.array(scores)

        composite[metric] = {
            'mean': np.mean(scores_array),
            'median': np.median(scores_array),
            'min': np.min(scores_array),
            'max': np.max(scores_array),
            'std': np.std(scores_array),
            'worst_page': np.argmin(scores_array) + 1 if metric != 'Skew Angle' else np.argmax(scores_array) + 1,
        }

    return composite

def print_legend():
    """Print score interpretation legend."""
    print("\n" + "="*70)
    print("SCORE INTERPRETATION LEGEND")
    print("="*70)

    legend = [
        ("Laplacian Variance", "0-1000+", "Good: >100, Marginal: 50-100, Poor: <50"),
        ("Tesseract Confidence", "0-100", "Good: >70, Marginal: 50-70, Poor: <50"),
        ("Contrast Ratio", "0-100+", "Good: >30, Marginal: 15-30, Poor: <15"),
        ("Edge Density", "0-100", "Good: >5, Marginal: 2-5, Poor: <2"),
        ("Signal-to-Noise Ratio", "0-50+", "Good: >15, Marginal: 8-15, Poor: <8"),
        ("Text Area Ratio", "0-100", "Good: >10, Marginal: 5-10, Poor: <5"),
        ("Skew Angle", "0-45°", "Good: <2°, Marginal: 2-5°, Poor: >5°"),
    ]

    for metric, range_val, interpretation in legend:
        print(f"\n{metric}:")
        print(f"  Range: {range_val}")
        print(f"  {interpretation}")

    print("="*70 + "\n")

def print_composite_summary(composite):
    """Print composite scores summary."""
    print("\n" + "="*70)
    print("COMPOSITE SCORES - DOCUMENT SUMMARY")
    print("="*70)
    print("\nAggregation across all analyzed pages:")
    print("-" * 70)

    for metric, stats in composite.items():
        print(f"\n{metric}:")
        print(f"  Mean (Average)............ {stats['mean']:>10.2f}  [{get_quality_rating(metric, stats['mean'])}]")
        print(f"  Median (Middle value)..... {stats['median']:>10.2f}  [{get_quality_rating(metric, stats['median'])}]")
        print(f"  Min (Best case)........... {stats['min']:>10.2f}  [{get_quality_rating(metric, stats['min'])}]")
        print(f"  Max (Worst case).......... {stats['max']:>10.2f}  [{get_quality_rating(metric, stats['max'])}]")
        print(f"  Std Dev (Consistency)..... {stats['std']:>10.2f}")
        print(f"  Worst performing page..... Page {stats['worst_page']}")

    print("\n" + "="*70)
    print("INTERPRETATION NOTES:")
    print("="*70)
    print("• Mean: Overall average quality across all pages")
    print("• Median: Middle value, less affected by outliers")
    print("• Min/Max: Range shows consistency (smaller range = more consistent)")
    print("• Std Dev: Lower values indicate more consistent quality across pages")
    print("• Worst Page: Identifies which page needs attention")
    print("\nRECOMMENDATION:")

    # Provide overall recommendation based on median scores
    poor_metrics = []
    marginal_metrics = []

    for metric, stats in composite.items():
        rating = get_quality_rating(metric, stats['median'])
        if rating == 'POOR':
            poor_metrics.append(metric)
        elif rating == 'MARGINAL':
            marginal_metrics.append(metric)

    if poor_metrics:
        print(f"⚠ POOR quality detected in: {', '.join(poor_metrics)}")
        print("  → Consider rejecting or requesting re-transmission")
    elif marginal_metrics:
        print(f"⚠ MARGINAL quality in: {', '.join(marginal_metrics)}")
        print("  → May require preprocessing before LLM analysis")
    else:
        print("✓ Document quality is GOOD across all metrics")
        print("  → Safe to send to LLM for processing")

    print("="*70 + "\n")

def main():
    parser = argparse.ArgumentParser(
        description='Analyze PDF fax quality using multiple image quality metrics.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('-i', '--input', required=True,
                        help='Input PDF file path')
    parser.add_argument('-n', '--num-pages', type=int, default=None,
                        help='Number of pages to analyze (default: all pages)')

    # Test flags (all enabled by default)
    parser.add_argument('-l', '--no-laplacian', action='store_true',
                        help='Disable Laplacian variance test')
    parser.add_argument('-t', '--no-tesseract', action='store_true',
                        help='Disable Tesseract confidence test')
    parser.add_argument('-c', '--no-contrast', action='store_true',
                        help='Disable contrast ratio test')
    parser.add_argument('-e', '--no-edge', action='store_true',
                        help='Disable edge density test')
    parser.add_argument('-s', '--no-snr', action='store_true',
                        help='Disable signal-to-noise ratio test')
    parser.add_argument('-x', '--no-text', action='store_true',
                        help='Disable text area ratio test')
    parser.add_argument('-k', '--no-skew', action='store_true',
                        help='Disable skew angle detection test')

    args = parser.parse_args()

    # Determine which tests are enabled
    tests = {
        'laplacian': not args.no_laplacian,
        'tesseract': not args.no_tesseract,
        'contrast': not args.no_contrast,
        'edge': not args.no_edge,
        'snr': not args.no_snr,
        'text': not args.no_text,
        'skew': not args.no_skew,
    }

    # Check if at least one test is enabled
    if not any(tests.values()):
        print("Error: At least one test must be enabled.", file=sys.stderr)
        sys.exit(1)

    # Open PDF and get page count
    try:
        doc = fitz.open(args.input)
        total_pages = len(doc)
        doc.close()
    except Exception as e:
        print(f"Error opening PDF: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine pages to analyze
    pages_to_analyze = args.num_pages if args.num_pages else total_pages
    pages_to_analyze = min(pages_to_analyze, total_pages)

    print(f"\nAnalyzing PDF: {args.input}")
    print(f"Total pages: {total_pages}")
    print(f"Analyzing: {pages_to_analyze} page(s)")
    print(f"Enabled tests: {', '.join([k.replace('_', ' ').title() for k, v in tests.items() if v])}")

    print_legend()

    # Store all results for composite calculation
    all_results = []

    # Analyze each page
    for page_num in range(pages_to_analyze):
        print(f"\n{'='*70}")
        print(f"PAGE {page_num + 1}")
        print(f"{'='*70}")

        try:
            # Convert page to image
            image = pdf_page_to_image(args.input, page_num)

            # Run analysis
            results = analyze_page(image, tests)
            all_results.append(results)

            # Print results with quality ratings
            for metric, score in results.items():
                rating = get_quality_rating(metric, score)
                print(f"{metric:.<40} {score:>10.2f}  [{rating}]")

        except Exception as e:
            print(f"Error analyzing page {page_num + 1}: {e}", file=sys.stderr)
            continue

    # Print composite summary if multiple pages were analyzed
    if len(all_results) > 1:
        composite = calculate_composite_scores(all_results)
        print_composite_summary(composite)

    print(f"\n{'='*70}")
    print("Analysis complete.")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
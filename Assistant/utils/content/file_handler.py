"""File handling utilities for chat attachments."""
import html
import PyPDF2
from typing import Tuple, Optional
from PIL import Image
from io import BytesIO

from config.config_loader  import config
from utils.core.structured_logger import get_logger

logger = get_logger(__name__)

def format_file_content(file_name: str, file_content: str) -> str:
    """Format file content for display in chat with proper HTML structure."""
    escaped_name = html.escape(file_name)
    escaped_content = html.escape(file_content)
    
    return (
        f'<details>'
        f'<summary>📎 Attached File: {escaped_name}</summary>'
        f'<div style="white-space: pre-wrap;">{escaped_content}</div>'
        f'</details>'
    )


def is_text_file(file_bytes: bytes, sample_size: int = 1024) -> bool:
    """Check if file content is text by analyzing the bytes."""
    sample = file_bytes[:sample_size]
    
    if not sample:
        return True  # Empty file, treat as text
    
    # Check for null bytes
    if b'\x00' in sample:
        return False
    
    # Try to decode as UTF-8
    try:
        sample.decode('utf-8')
        return True
    except UnicodeDecodeError:
        pass
    
    # Try other common encodings
    for encoding in ['latin-1', 'cp1252', 'ascii']:
        try:
            sample.decode(encoding)
            # Check if it contains mostly printable characters
            text = sample.decode(encoding)
            printable_ratio = sum(c.isprintable() or c.isspace() for c in text) / len(text)
            if printable_ratio > 0.85:  # 85% printable characters
                return True
        except (UnicodeDecodeError, AttributeError):
            continue
    
    return False


def is_image_file(filename: str) -> bool:
    """Check if file is a supported image format by extension."""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.ico'}
    return any(filename.lower().endswith(ext) for ext in image_extensions)


def is_pdf_file(filename: str) -> bool:
    """Check if file is a PDF by extension."""
    return filename.lower().endswith('.pdf')


def decode_text_file(file_bytes: bytes) -> Optional[str]:
    """Attempt to decode file bytes as text using multiple encodings."""
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
    
    for encoding in encodings:
        try:
            return file_bytes.decode(encoding)
        except (UnicodeDecodeError, AttributeError):
            continue
    
    return None


def process_uploaded_file(uploaded_file) -> Tuple[str, Optional[str], Optional[Image.Image], Optional[bytes]]:
    """Process an uploaded file and return appropriate format."""
    filename = uploaded_file.name

    try:
        file_bytes = uploaded_file.read()

        # Check file size (add size limits)
        file_size_mb = len(file_bytes) / (1024 * 1024)
        max_file_size_mb = config.get('app.max_file_size_mb', 3)
        
        if file_size_mb > max_file_size_mb:
            raise ValueError(f"File too large ({file_size_mb:.1f}MB). Maximum size: {max_file_size_mb}MB")

        # Reset file pointer for potential re-reading
        uploaded_file.seek(0)

    except Exception as e:
        logger.error("file_read_error", filename=filename, error=str(e))
        raise ValueError(f"Could not read file: {str(e)}")

    # Check for images first (by extension, then try to open)
    if is_image_file(filename):
        try:
            image = Image.open(BytesIO(file_bytes))
            # Convert to RGB if necessary
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            return 'image', None, image, None
        except Exception as e:
            logger.error("image_processing_error", filename=filename, error=str(e))
            raise ValueError(f"Invalid image file: {str(e)}")

    # Check for PDFs
    if is_pdf_file(filename):
        try:
            # Verify it's actually a valid PDF
            PyPDF2.PdfReader(BytesIO(file_bytes))
            return 'pdf', None, None, file_bytes
        except Exception as e:
            logger.error("pdf_processing_error", filename=filename, error=str(e))
            raise ValueError(f"Invalid PDF file: {str(e)}")

    # Check if it's a text file by content analysis
    if is_text_file(file_bytes):
        try:
            text_content = decode_text_file(file_bytes)
            if text_content is not None:
                return 'text', text_content, None, None
        except Exception as e:
            logger.error("text_processing_error", filename=filename, error=str(e))
            raise ValueError(f"Could not decode text file: {str(e)}")

    return 'unsupported', None, None, None


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    """Get the number of pages in a PDF."""
    try:
        pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
        return len(pdf_reader.pages)
    except Exception:
        return 0
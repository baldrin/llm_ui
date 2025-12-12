"""
PDF handling utilities for size calculation and encoding.
"""

import base64
import hashlib
from typing import Optional, Dict, Any
import streamlit as st

from utils.core.structured_logger import get_logger
from utils.content.file_handler import get_pdf_page_count

logger = get_logger(__name__)


class PDFHandler:
    """
    Handles PDF size and token calculations with caching.
    Caches metadata only (not encoded strings).
    """

    # Token estimation constant
    TOKENS_PER_PAGE = 800 #Needs to be configurable or a more precise way to calculate this found

    def __init__(self):
        """Initialize the PDF handler with caching."""
        logger.debug("pdf_handler_initialized")

    def _get_pdf_hash(self, pdf_bytes: bytes) -> str:
        """Generate hash from PDF bytes for cache key."""
        pdf_hash = hashlib.md5(pdf_bytes).hexdigest()

        logger.debug(
            "pdf_hash_generated",
            hash=pdf_hash[:8],
            size_bytes=len(pdf_bytes)
        )

        return pdf_hash    

    def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached PDF metadata if exists."""
        cache = st.session_state.pdf_metadata_cache

        if key in cache:
            logger.debug(
                "pdf_metadata_from_cache",
                hash=key[:8]
            )
            return cache[key].copy()

        return None

    def _set_in_cache(self, key: str, value: Dict[str, Any]) -> None:
        """Store PDF metadata in cache."""
        import time

        st.session_state.pdf_metadata_cache[key] = {
            **value,
            'cached_at': time.time()
        }

        logger.debug(
            "pdf_metadata_cached",
            hash=key[:8],
            payload_size_bytes=value.get('payload_size_bytes'),
            pages=value.get('pages')
        )

    def estimate_pdf_metadata(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Calculate PDF metadata with caching.

        Returns:
            {
                'payload_size_bytes': int,  # Base64 size
                'file_size_bytes': int,     # Original PDF size
                'pages': int,               # Page count
                'tokens': int               # Estimated tokens
            }
        """
        pdf_hash = self._get_pdf_hash(pdf_bytes)

        cached_result = self._get_from_cache(pdf_hash)
        if cached_result:
            result = {k: v for k, v in cached_result.items() if k != 'cached_at'}
            return result

        logger.debug("pdf_metadata_calculating", hash=pdf_hash[:8])

        try:
            pages = get_pdf_page_count(pdf_bytes)

            if pages == 0:
                logger.error(
                    "pdf_page_count_failed",
                    hash=pdf_hash[:8],
                    reason="zero_pages"
                )
                raise ValueError("Could not count PDF pages - file may be corrupt")

            file_size_bytes = len(pdf_bytes)
            payload_size_bytes = len(base64.b64encode(pdf_bytes))

            tokens = pages * self.TOKENS_PER_PAGE

            result = {
                'payload_size_bytes': payload_size_bytes,
                'file_size_bytes': file_size_bytes,
                'pages': pages,
                'tokens': tokens
            }

            self._set_in_cache(pdf_hash, result)

            logger.debug(
                "pdf_metadata_calculated",
                hash=pdf_hash[:8],
                pages=pages,
                file_size_kb=round(file_size_bytes / 1024, 2),
                payload_size_kb=round(payload_size_bytes / 1024, 2),
                tokens=tokens
            )

            return result

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "pdf_metadata_calculation_failed",
                hash=pdf_hash[:8],
                error_type=type(e).__name__,
                error=str(e)
            )
            raise ValueError(f"Failed to process PDF: {str(e)}")
        
    def encode_pdf(self, pdf_bytes: bytes) -> str:
        """Encode PDF to base64 string for API requests."""
        pdf_size = len(pdf_bytes)

        logger.debug(
            "encoding_pdf",
            pdf_bytes=pdf_size,
            pdf_kb=round(pdf_size / 1024, 2)
        )

        encoded = base64.b64encode(pdf_bytes).decode('utf-8')

        logger.debug(
            "pdf_encoded",
            encoded_bytes=len(encoded),
            encoded_kb=round(len(encoded) / 1024, 2)
        )

        return encoded
    
# Module-level instance for easy imports
pdf_handler = PDFHandler()
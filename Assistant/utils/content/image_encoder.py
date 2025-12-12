"""
Image encoding utilities for LLM API requests.
"""

import base64
from io import BytesIO
from typing import Tuple, List, Optional
from PIL import Image
import hashlib
import streamlit as st

from utils.core.structured_logger import get_logger

logger = get_logger(__name__)

def get_encoder(max_size_bytes: int = 3_500_000) -> 'ImageEncoder':
    """Get or create encoder instance from session state."""
    # Store in session state for user isolation
    if 'image_encoder' not in st.session_state:
        st.session_state.image_encoder = ImageEncoder(max_image_size_bytes=max_size_bytes)
        logger.debug("image_encoder_created_for_session")

    return st.session_state.image_encoder

class ImageEncoder:
    """
    Encodes PIL Images for LLM API requests    
    Designed to work within 4MB request size limits.
    """

    def __init__(self, max_image_size_bytes: int = 3_500_000):
        self.max_image_size_bytes = max_image_size_bytes
        self.MAX_DIMENSION = 2000 
        self._init_cache()

        logger.debug(
            "image_encoder_initialized",
            max_size_mb=round(max_image_size_bytes / 1_000_000, 2)
        )

    def _init_cache(self):
        """Initialize image metadata cache in session state if not exists."""
        if 'image_metadata_cache' not in st.session_state:
            st.session_state.image_metadata_cache = {}
            logger.debug("image_cache_initialized")

    def estimate_encoded_size(self, image: Image.Image) -> dict:
        """
        Estimate the encoded size of an image without fully encoding it.
        Resizes if needed and caches results.
        """
        buffer = None
        try:
            # Resize if exceeds max dimensions
            original_size = (image.width, image.height)
            resized = False

            if image.width > self.MAX_DIMENSION or image.height > self.MAX_DIMENSION:
                image = image.copy()
                image.thumbnail((self.MAX_DIMENSION, self.MAX_DIMENSION), Image.Resampling.LANCZOS)
                resized = True
                logger.debug(
                    "image_resized",
                    original_size=original_size,
                    new_size=(image.width, image.height)
                )

            # Generate cache key from image data
            image_hash = hashlib.md5(image.tobytes()).hexdigest()

            # Check cache first
            cached_result = self._get_from_cache(image_hash)
            if cached_result:
                # Remove timestamp before returning
                result = {k: v for k, v in cached_result.items() if k != 'cached_at'}
                return result

            # Determine format based on transparency
            has_transparency = self._has_transparency(image)

            if has_transparency:
                output_format = "PNG"
                processed_image = self._prepare_for_png(image, image.mode)
                buffer = BytesIO()
                processed_image.save(buffer, format="PNG", optimize=True)
            else:
                output_format = "JPEG"
                processed_image = self._prepare_for_jpeg(image, image.mode)
                buffer = BytesIO()
                processed_image.save(buffer, format="JPEG", quality=85, optimize=True)

            buffer.seek(0)
            file_bytes = buffer.getvalue()
            file_size_bytes = len(file_bytes)
            payload_size_bytes = len(base64.b64encode(file_bytes))

            result = {
                'payload_size_bytes': payload_size_bytes,  # Base64 size - for 4MB check
                'file_size_bytes': file_size_bytes,        # JPEG/PNG size
                'format': output_format,
                'resized': resized
            }

            # Cache the result
            self._set_in_cache(image_hash, result)

            logger.debug(
                "image_size_estimated",
                format=output_format,
                file_size_bytes=file_size_bytes,
                payload_size_bytes=payload_size_bytes,
                resized=resized
            )

            return result

        finally:
            # Clean up buffer
            if buffer:
                buffer.close()

    def _get_from_cache(self, key: str) -> Optional[dict]:
        """Get cached image metadata if exists."""
        cache = st.session_state.image_metadata_cache

        if key in cache:
            logger.debug(
                "image_metadata_from_cache",
                hash=key[:8]
            )
            return cache[key].copy()

        return None

    def _set_in_cache(self, key: str, value: dict) -> None:
        """Store image metadata in cache."""
        import time

        st.session_state.image_metadata_cache[key] = {
            **value,
            'cached_at': time.time()
        }

        logger.debug(
            "image_metadata_cached",
            hash=key[:8],
            payload_size_bytes=value.get('payload_size_bytes'),
            format=value.get('format')
        )

    def estimate_total_size(self, images: List[Image.Image]) -> dict:
        """Estimate total encoded size for multiple images."""
        results = []
        total_bytes = 0

        for idx, image in enumerate(images):
            try:
                result = self.estimate_encoded_size(image)
                results.append(result)
                total_bytes += result['payload_size_bytes']
            except Exception as e:
                logger.error(
                    "image_size_estimation_failed",
                    image_index=idx,
                    error=str(e)
                )
                
                continue

        return {
            'total_bytes': total_bytes,
            'total_kb': round(total_bytes / 1024, 2),
            'total_mb': round(total_bytes / 1_000_000, 2),
            'images': results,
            'count': len(results)
        }

    def encode_image(self, image: Image.Image) -> Tuple[str, str]:
        """Encode PIL Image to base64 string with optimal format."""
        original_mode = image.mode
        original_size = image.size

        logger.debug(
            "encoding_image",
            mode=original_mode,
            size=f"{original_size[0]}x{original_size[1]}"
        )

        # Check if image actually uses transparency
        has_transparency = self._has_transparency(image)

        if has_transparency:
            # Must use PNG to preserve transparency
            output_format = "PNG"
            processed_image = self._prepare_for_png(image, original_mode)
            buffer = BytesIO()
            processed_image.save(buffer, format="PNG", optimize=True)

        else:
            # Use JPEG for smaller file size (5-10x reduction)
            output_format = "JPEG"
            processed_image = self._prepare_for_jpeg(image, original_mode)
            buffer = BytesIO()
            processed_image.save(buffer, format="JPEG", quality=85, optimize=True)

        buffer.seek(0)
        encoded_size = len(buffer.getvalue())

        # Validate size
        if encoded_size > self.max_image_size_bytes:
            logger.error(
                "image_too_large",
                format=output_format,
                size_mb=round(encoded_size / 1_000_000, 2),
                max_mb=round(self.max_image_size_bytes / 1_000_000, 2)
            )
            raise ValueError(
                f"Encoded image ({round(encoded_size / 1_000_000, 2)}MB) "
                f"exceeds maximum size ({round(self.max_image_size_bytes / 1_000_000, 2)}MB)"
            )

        # Warn if approaching limit
        if encoded_size > self.max_image_size_bytes * 0.8:
            logger.warning(
                "image_size_warning",
                format=output_format,
                size_mb=round(encoded_size / 1_000_000, 2),
                percent_of_limit=round(encoded_size / self.max_image_size_bytes * 100, 1)
            )

        logger.debug(
            "image_encoded",
            format=output_format,
            encoded_bytes=encoded_size,
            encoded_kb=round(encoded_size / 1024, 2),
            encoded_mb=round(encoded_size / 1_000_000, 2)
        )

        encoded_string = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return encoded_string, output_format

    def _has_transparency(self, image: Image.Image) -> bool:
        """Check if image actually uses transparency."""
        if image.mode == 'RGBA':
            # Check if alpha channel has any non-opaque pixels
            alpha = image.split()[3]
            return alpha.getextrema()[0] < 255

        elif image.mode == 'LA':
            # Grayscale with alpha
            alpha = image.split()[1]
            return alpha.getextrema()[0] < 255

        elif image.mode == 'P':
            # Palette mode - check for transparency info
            return 'transparency' in image.info

        return False

    def _prepare_for_jpeg(self, image: Image.Image, original_mode: str) -> Image.Image:
        """Prepare image for JPEG encoding (RGB or grayscale only)."""
        if image.mode == 'RGBA':
            # Composite onto white background
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            logger.debug(
                "image_converted",
                from_mode="RGBA",
                to_mode="RGB",
                reason="alpha_composited"
            )
            return background

        elif image.mode not in ('RGB', 'L'):
            # Convert to RGB
            converted = image.convert('RGB')
            logger.debug(
                "image_converted",
                from_mode=original_mode,
                to_mode="RGB"
            )
            return converted

        return image

    def _prepare_for_png(self, image: Image.Image, original_mode: str) -> Image.Image:
        """Prepare image for PNG encoding."""
        # PNG supports most modes, only convert if necessary
        if image.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P'):
            target_mode = 'RGBA' if 'A' in original_mode else 'RGB'
            converted = image.convert(target_mode)
            logger.debug(
                "image_converted",
                from_mode=original_mode,
                to_mode=target_mode
            )
            return converted

        return image


# Convenience functions

def estimate_image_size(image: Image.Image, max_size_bytes: int = 3_500_000) -> dict:
    """Convenience function to estimate a single image's encoded size."""
    encoder = get_encoder(max_size_bytes)
    return encoder.estimate_encoded_size(image)

def estimate_images_total_size(images: List[Image.Image], max_size_bytes: int = 3_500_000) -> dict:
    """Convenience function to estimate total size for multiple images."""
    encoder = get_encoder(max_size_bytes)
    return encoder.estimate_total_size(images)

def encode_image(image: Image.Image, max_size_bytes: int = 3_500_000) -> Tuple[str, str]:
    """Convenience function to encode a single image."""
    encoder = get_encoder(max_size_bytes)
    return encoder.encode_image(image)
"""
Shared image utilities for dimension calculations and resizing logic.
"""
from typing import Tuple
from utils.core.structured_logger import get_logger

logger = get_logger(__name__)


def calculate_resized_dimensions(
    width: int,
    height: int,
    max_dimension: int = 2000
) -> Tuple[int, int, bool]:
    """Calculate dimensions after thumbnail resize."""
    # Check if resize is needed
    if width <= max_dimension and height <= max_dimension:
        return width, height, False

    # Calculate scaling ratio (same logic as PIL thumbnail)
    if width > height:
        ratio = max_dimension / width
    else:
        ratio = max_dimension / height

    new_width = int(width * ratio)
    new_height = int(height * ratio)

    logger.debug(
        "dimensions_calculated",
        original=f"{width}x{height}",
        resized=f"{new_width}x{new_height}",
        ratio=round(ratio, 3),
        max_dimension=max_dimension
    )

    return new_width, new_height, True


def get_image_dimensions_for_encoding(
    width: int,
    height: int,
    max_dimension: int = 2000
) -> Tuple[int, int]:
    """Get the final dimensions that will be used for encoding."""
    new_width, new_height, _ = calculate_resized_dimensions(
        width, height, max_dimension
    )
    return new_width, new_height
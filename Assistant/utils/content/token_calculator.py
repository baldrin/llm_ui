"""
Token calculation utilities for text, images, and PDFs.
"""
from typing import Optional
from PIL import Image

from utils.core.structured_logger import get_logger

logger = get_logger(__name__)


class TokenCalculator:
    """
    Handles all token calculations for different content types.
    
    Token estimation formulas:
    - Text: ~4 characters per token (rough estimate)
    - Images: (width × height) / 750 (Anthropic formula)
    - PDFs: ~800 tokens per page (rough estimate, varies by content)
    """
    
    # Constants for token estimation
    CHARS_PER_TOKEN = 4
    IMAGE_PIXELS_PER_TOKEN = 750
    PDF_TOKENS_PER_PAGE = 800
    
    @staticmethod
    def estimate_text_tokens(text: str) -> int:
        """Estimate tokens for text content."""
        if not text:
            return 0
        
        estimated = len(text) // TokenCalculator.CHARS_PER_TOKEN
        
        logger.debug(
            "text_tokens_estimated",
            text_length=len(text),
            estimated_tokens=estimated
        )
        
        return estimated
    
    @staticmethod
    def estimate_image_tokens(image: Image.Image) -> int:
        """Estimate tokens for an image based on its dimensions."""
        if not image:
            return 0
        
        width, height = image.size
        pixels = width * height
        tokens = pixels / TokenCalculator.IMAGE_PIXELS_PER_TOKEN
        
        logger.debug(
            "image_tokens_estimated",
            width=width,
            height=height,
            pixels=pixels,
            estimated_tokens=int(tokens)
        )
        
        return int(tokens)
    
    @staticmethod
    def estimate_pdf_tokens(pages: int) -> int:
        """Estimate tokens for a PDF based on page count."""
        if pages <= 0:
            return 0
        
        tokens = pages * TokenCalculator.PDF_TOKENS_PER_PAGE
        
        logger.debug(
            "pdf_tokens_estimated",
            pages=pages,
            tokens_per_page=TokenCalculator.PDF_TOKENS_PER_PAGE,
            estimated_tokens=tokens
        )
        
        return tokens
    
    @staticmethod
    def estimate_message_tokens(
        text: str,
        images: Optional[list] = None,
        pdfs: Optional[list] = None
    ) -> int:
        """Estimate total tokens for a complete message with attachments."""
        total_tokens = 0
        
        # Text tokens
        text_tokens = TokenCalculator.estimate_text_tokens(text)
        total_tokens += text_tokens
        
        # Image tokens
        image_tokens = 0
        if images:
            for image in images:
                if isinstance(image, dict):
                    # Handle dict format with 'image' key
                    image = image.get('image')
                if image:
                    image_tokens += TokenCalculator.estimate_image_tokens(image)
        total_tokens += image_tokens
        
        # PDF tokens
        pdf_tokens = 0
        if pdfs:
            from utils.content.pdf_handler import pdf_handler

            for pdf_info in pdfs:
                if isinstance(pdf_info, dict):
                    pdf_bytes = pdf_info.get('bytes')
                    if pdf_bytes:
                        try:
                            metadata = pdf_handler.estimate_pdf_metadata(pdf_bytes)
                            pdf_tokens += metadata['tokens']
                        except Exception as e:
                            # If we can't get metadata, use fallback
                            logger.warning(
                                "pdf_token_estimation_failed",
                                error=str(e)
                            )
                            # Fallback: assume 1 page
                            pdf_tokens += TokenCalculator.estimate_pdf_tokens(1)
        total_tokens += pdf_tokens
        
        logger.debug(
            "message_tokens_estimated",
            text_tokens=text_tokens,
            image_tokens=image_tokens,
            pdf_tokens=pdf_tokens,
            total_tokens=total_tokens,
            image_count=len(images) if images else 0,
            pdf_count=len(pdfs) if pdfs else 0
        )
        
        return total_tokens
    
    @staticmethod
    def get_actual_tokens_from_message(message: dict) -> tuple[int, int]:
        """Extract actual token counts from an LLM response message."""
        input_tokens = message.get('input_tokens', 0)
        output_tokens = message.get('output_tokens', 0)
        
        return input_tokens, output_tokens
    
    @staticmethod
    def calculate_total_conversation_tokens(messages: list) -> int:
        """Calculate total tokens for an entire conversation."""
        total_tokens = 0
        
        for msg in messages:
            # Try to use actual tokens first
            input_tokens = msg.get('input_tokens', 0)
            output_tokens = msg.get('output_tokens', 0)
            
            if input_tokens > 0 or output_tokens > 0:
                # Use actual tokens
                total_tokens += input_tokens + output_tokens
            else:
                # Fall back to estimation
                content = msg.get('content', '')
                if isinstance(content, str):
                    total_tokens += TokenCalculator.estimate_text_tokens(content)
        
        logger.debug(
            "conversation_tokens_calculated",
            message_count=len(messages),
            total_tokens=total_tokens
        )
        
        return total_tokens

# Module-level instance for easy imports
token_calculator = TokenCalculator()
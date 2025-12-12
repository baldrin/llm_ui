"""
Service layer for LLM interactions.
"""
from typing import List, Dict, Any, Optional, Iterator, Union
from services.llm_client import LLMClient
from config.exceptions import LLMError
from utils.core.structured_logger import get_logger

logger = get_logger(__name__)

class LLMService:
    """Service layer to interface with the LLMAppKit's LLMClient."""

    def __init__(self) -> None:
        """Initialize the LLM service with a client."""
        self.client: LLMClient = LLMClient()

    def generate_completion(
        self, 
        messages: List[Dict[str, Any]], 
        temperature: float = 0.4, 
        max_tokens: int = 4096, 
        stream: bool = False, 
        llm_model: Optional[str] = None
    ) -> Union[Any, Iterator[Any]]:
        """
        Proxy method to the underlying LLMClient with token usage tracking.

        Args:
            messages: List of pre-processed message dictionaries with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            llm_model: Optional model identifier to use

        Returns:
            Response object (or iterator if streaming)

        Raises:
            LLMError: If LLM API call fails
        """
        try:
            response = self.client.generate_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                llm_model=llm_model
            )

            return response

        except Exception as e:
            logger.error("LLM API error", error=str(e))
            raise LLMError(
                "Failed to generate LLM completion",
                details={
                    "model": llm_model,
                    "message_count": len(messages),
                    "error": str(e)
                }
            )
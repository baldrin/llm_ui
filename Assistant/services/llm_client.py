"""
LLM client for OpenAI-compatible APIs (Databricks) with PDF and image support.
"""
import openai
import httpx
from typing import List, Dict, Any, Optional, Iterator, Union

from config.config_loader import config
from utils.core.structured_logger import get_logger

logger = get_logger(__name__)

class LLMClient:
    """
    Client for interacting with LLM APIs.

    Configured for Databricks serving endpoints but compatible with
    any OpenAI-compatible API.
    """

    def __init__(self) -> None:
        """Initialize the LLM client with Databricks configuration."""
        logger.debug("llm_client_initializing")

        certs_path = config.get("databricks.certs_path")
        api_key = config.get("databricks.token")
        base_url = config.get("databricks.base_url")

        if not all([certs_path, api_key, base_url]):
            logger.error(
                "llm_client_init_failed",
                has_certs=bool(certs_path),
                has_api_key=bool(api_key),
                has_base_url=bool(base_url)
            )
            raise ValueError("Missing required environment variables for LLM client")

        client = httpx.Client(verify=certs_path)
        self.client: openai.OpenAI = openai.OpenAI(
            api_key=api_key, 
            base_url=base_url, 
            http_client=client
        )
        self.llm_model: Optional[str] = None

        logger.info(
            "llm_client_initialized",
            base_url=base_url,
            has_default_model=self.llm_model is not None
        )

    def generate_completion(
        self, 
        messages: List[Dict[str, Any]], 
        temperature: float = 0.4, 
        max_tokens: int = 4096, 
        stream: bool = False, 
        llm_model: Optional[str] = None
    ) -> Union[Any, Iterator[Any]]:
        """
        Generate a completion from the LLM.

        Args:
            messages: List of pre-processed message dictionaries with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            llm_model: Model identifier (uses instance default if None)
        """
        if llm_model is None:
            llm_model = self.llm_model

        logger.debug(
            "llm_request_starting",
            model=llm_model,
            message_count=len(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream
        )

        params: Dict[str, Any] = {
            "model": llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }

        try:
            logger.info(
                "llm_request_sent",
                model=llm_model,
                stream=stream
            )

            response = self.client.chat.completions.create(**params)

            if not stream:
                # For non-streaming, we can log token usage
                if hasattr(response, 'usage'):
                    logger.info(
                        "llm_request_completed",
                        model=llm_model,
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens
                    )
                else:
                    logger.info("llm_request_completed", model=llm_model)
            else:
                logger.debug("llm_stream_started", model=llm_model)

            return response

        except Exception as e:
            logger.error(
                "llm_request_failed",
                model=llm_model,
                error_type=type(e).__name__,
                error_message=str(e),
                stream=stream
            )
            raise
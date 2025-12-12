from typing import List, Dict
from config.config_loader import config
from utils.core.structured_logger import get_logger

logger = get_logger(__name__)


def get_chat_title(messages: List[Dict]) -> str:
    """Generate a title based on the first user message or using LLM."""
    # Check if LLM title generation is enabled
    title_gen_enabled = config.get('title_generation.enabled', False)
    
    if not title_gen_enabled:
        return _get_simple_title(messages)
    
    # Try LLM generation
    try:
        from services.llm_service import LLMService
        llm_service = LLMService()
        model_id = config.get('title_generation.model')
        
        if not model_id:
            logger.warning("title_generation_no_model_configured")
            return _get_simple_title(messages)
        
        title = generate_title_with_llm(messages, model_id, llm_service)
        logger.info("title_generated_with_llm", title=title, model=model_id)
        return title
        
    except Exception as e:
        logger.error("title_generation_failed", error=str(e))
        return _get_simple_title(messages)


def _get_simple_title(messages: List[Dict]) -> str:
    """Generate a simple title based on the first user message."""
    for msg in messages:
        if msg["role"] == "user":
            content = msg["content"]
            
            # Remove file attachment HTML
            if "<details>" in content:
                parts = content.split("</details>")
                if len(parts) > 1:
                    content = parts[-1].strip()
            
            # Remove image/PDF indicators
            if content.startswith("🖼️") or content.startswith("📄"):
                lines = content.split("\n")
                if len(lines) > 2:
                    content = "\n".join(lines[2:]).strip()
            
            title = content[:30]
            return title + ("..." if len(content) > 30 else "")
    
    return "New Chat"


def generate_title_with_llm(
    messages: List[Dict], 
    model_id: str, 
    llm_service
) -> str:
    """Generate a concise title using the LLM."""
    # Get first few messages
    formatted_conversation = []
    for msg in messages[:4]:
        if "content" in msg and msg.get("content"):
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content")
            
            # Clean up content
            if "<details>" in content:
                parts = content.split("</details>")
                if len(parts) > 1:
                    content = parts[-1].strip()
            
            if content.startswith("🖼️") or content.startswith("📄"):
                lines = content.split("\n")
                if len(lines) > 2:
                    content = "\n".join(lines[2:]).strip()
            
            formatted_conversation.append(f"{role}: {content[:200]}")
    
    combined_message = "\n\n".join(formatted_conversation)
    if len(combined_message) > 800:
        combined_message = combined_message[:800] + "..."

    # Get configuration
    max_tokens = config.get('title_generation.max_tokens', 20)
    temperature = config.get('title_generation.temperature', 0.3)

    prompt = [
        {
            "role": "user",
            "content": f"Generate a 2-4 word title for this conversation. Respond with ONLY the title, nothing else:\n\n{combined_message}"
        }
    ]

    try:
        logger.debug("generating_title_with_llm", model=model_id, max_tokens=max_tokens)
        
        response = llm_service.generate_completion(
            messages=prompt,
            stream=False,
            llm_model=model_id,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        # Simple extraction - just get the content as string
        title = str(response.choices[0].message.content).strip()
        
        # Remove quotes
        title = title.strip("\"'")
        
        # Validate
        if len(title) > 50:
            title = title[:50]
        
        if not title or title.isspace():
            raise ValueError("Empty title")
        
        logger.info("title_generated_successfully", title=title)
        return title
        
    except Exception as e:
        logger.error("llm_title_generation_error", error=str(e), model=model_id)
        raise
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass

from config.constants import CONTEXT_WINDOW_SIZE
from config.types import MessageDict
from utils.core.structured_logger import get_logger
from utils.content.token_calculator import token_calculator
from utils.content.pdf_handler import pdf_handler

logger = get_logger(__name__)


@dataclass
class ContextStatus:
    """Status of context window usage for UI display."""
    total_tokens: int
    percentage: float
    can_accept_input: bool
    warning_message: Optional[str]
    color: str
    status: str  # 'ok', 'warning', 'critical', 'full'


@dataclass
class ValidationResult:
    """Result of validation check."""
    can_send: bool
    error_message: Optional[str]
    details: Dict[str, Any]


class ContextManager:
    """
    Handles:
    - Token validation (uses token_calculator for calculations)
    - Request size calculations
    - Validation (tokens + request size)
    - UI status generation
    
    Thresholds:
    - 0-75%: OK (green)
    - 75-90%: Warning (yellow)
    - 90-100%: Critical (orange/red)
    - 100%: Hard limit - block completely (red)
    """
    
    # Token thresholds
    WARNING_THRESHOLD = 0.75
    CRITICAL_THRESHOLD = 0.90
    HARD_LIMIT = 0.999 # 100%
    
    # Request size limit (4MB)
    MAX_REQUEST_SIZE_BYTES = 4194304
    
    def __init__(self, context_window_size: int = CONTEXT_WINDOW_SIZE):
        """
        Initialize context manager.
        
        Args:
            context_window_size: Maximum context window size in tokens
        """
        self.context_window_size = context_window_size
        logger.debug(
            "context_manager_initialized",
            context_window_size=context_window_size
        )
    
    def get_current_tokens(self, messages: List[MessageDict]) -> int:
        """Get current token count from LLM-reported usage."""
        if not messages:
            return 0
        
        # Find the LAST assistant message
        for i in reversed(range(len(messages))):
            if messages[i].get('role') == 'assistant':
                input_tokens = messages[i].get('input_tokens', 0)
                output_tokens = messages[i].get('output_tokens', 0)
                
                if input_tokens > 0:
                    total_tokens = input_tokens + output_tokens
                    
                    logger.debug(
                        "current_tokens_from_llm",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        total_tokens=total_tokens
                    )
                    
                    return total_tokens
        
        # No assistant messages with token counts yet
        return 0
    
    def estimate_total_with_new_message(
        self,
        messages: List[MessageDict],
        new_message: str,
        include_system_prompt: bool = True,
        attachments: Optional[Dict[str, List[Any]]] = None
    ) -> int:
        """Estimate total tokens if a new message is added."""
        from utils.chat.prompt_loader import prompt_loader

        if attachments:
            logger.debug(
                "attachments_debug",
                has_images=bool(attachments.get('images')),
                image_count=len(attachments.get('images', [])),
                has_pdfs=bool(attachments.get('pdfs')),
                pdf_count=len(attachments.get('pdfs', []))
            )
        
        # Start with current actual tokens
        current_tokens = self.get_current_tokens(messages)
        
        # Add system prompt if needed (only if this is first message)
        system_prompt_tokens = 0
        if include_system_prompt and len(messages) == 0:
            system_prompt = prompt_loader.get_system_prompt()
            if system_prompt:
                system_prompt_tokens = token_calculator.estimate_text_tokens(system_prompt)
        
        # Calculate new message tokens (including attachments)
        new_message_tokens = token_calculator.estimate_message_tokens(
            text=new_message,
            images=attachments.get('images') if attachments else None,
            pdfs=attachments.get('pdfs') if attachments else None
        )
        
        total_estimated = (
            current_tokens + 
            system_prompt_tokens + 
            new_message_tokens
        )
        
        logger.debug(
            "total_tokens_estimated",
            current_tokens=current_tokens,
            system_prompt_tokens=system_prompt_tokens,
            new_message_tokens=new_message_tokens,
            total_estimated=total_estimated
        )
        
        return total_estimated
    
    def estimate_request_size(
        self,
        messages: List[MessageDict],
        new_message: Optional[str] = None,
        attachments: Optional[Dict[str, List[Any]]] = None
    ) -> int:
        """
        Estimate total request size in bytes for LLM API call.
        """
        from utils.content.image_encoder import estimate_image_size
        
        total_size = 0
        
        # Existing messages
        for msg in messages:
            content = str(msg.get('content', ''))
            total_size += len(content.encode('utf-8'))
        
        # New message text
        if new_message:
            total_size += len(new_message.encode('utf-8'))
        
        # Attachments
        if attachments:
            # Images
            for image_info in attachments.get('images', []):
                image = image_info.get('image')
                if image:
                    try:
                        size_info = estimate_image_size(image)
                        total_size += int(size_info['payload_size_bytes'])
                    except Exception as e:
                        logger.warning("image_size_estimation_failed", error=str(e))
                        total_size += 1_000_000  # 1MB fallback
            
            # PDFs
            for pdf_info in attachments.get('pdfs', []):
                pdf_bytes = pdf_info.get('bytes')
                if pdf_bytes:
                    try:
                        metadata = pdf_handler.estimate_pdf_metadata(pdf_bytes)
                        total_size += metadata['payload_size_bytes']
                    except Exception as e:
                        logger.error(
                            "pdf_metadata_failed",
                            error_type=type(e).__name__,
                            error=str(e)
                        )
                        raise  # Block the upload
        
        logger.debug(
            "request_size_estimated",
            total_kb=round(total_size / 1024, 2)
        )
        
        return total_size
    
    def validate_can_send(
        self,
        messages: List[MessageDict],
        new_message: str,
        attachments: Optional[Dict[str, List[Any]]] = None
    ) -> ValidationResult:
        """SINGLE validation method that checks ALL constraints."""
        details = {}
        
        current_tokens = self.get_current_tokens(messages)
        projected_tokens = self.estimate_total_with_new_message(
            messages, 
            new_message,
            attachments=attachments
        )
        
        percentage = projected_tokens / self.context_window_size
        
        details['current_tokens'] = current_tokens
        details['projected_tokens'] = projected_tokens
        details['percentage'] = percentage * 100
        details['context_window_size'] = self.context_window_size
        
        # Check if message would exceed token limit
        if percentage >= self.HARD_LIMIT:
            error_message = (
                "🛑 **Message Too Large**\n\n"
                f"Your message would bring the conversation to **{percentage*100:.1f}%** "
                f"of the context limit ({projected_tokens:,} / {self.context_window_size:,} tokens).\n\n"
                "**Options:**\n"
                "- You can copy your message using the copy icon in the upper right corner of the text box above\n"
                "- Start a new conversation\n"
                "- Break your message into smaller parts"
            )
            
            details['reason'] = 'token_limit_exceeded'
            details['block_type'] = 'message_too_large'
            
            logger.warning(
                "message_blocked_token_limit",
                current_tokens=current_tokens,
                projected_tokens=projected_tokens,
                percentage=percentage * 100
            )
            
            return ValidationResult(
                can_send=False,
                error_message=error_message,
                details=details
            )
    
        request_size = self.estimate_request_size(
            messages,
            new_message,
            attachments
        )
        
        details['request_size_bytes'] = request_size
        details['request_size_mb'] = request_size / (1024 * 1024)
        details['max_request_size_mb'] = self.MAX_REQUEST_SIZE_BYTES / (1024 * 1024)
        
        if request_size > self.MAX_REQUEST_SIZE_BYTES:
            error_message = (
                "🛑 **Request Too Large**\n\n"
                "Your message plus attachments exceed the 4MB limit "
                f"({request_size / (1024 * 1024):.2f}MB).\n\n"
                "**Options:**\n"
                "- Remove some attachments\n"
                "- Start a new conversation\n"
                "- Reduce the size of your message"
            )
            
            details['reason'] = 'request_size_exceeded'
            details['block_type'] = 'request_too_large'
            
            logger.warning(
                "message_blocked_request_size",
                request_size_bytes=request_size,
                request_size_mb=request_size / (1024 * 1024),
                has_attachments=bool(attachments)
            )
            
            return ValidationResult(
                can_send=False,
                error_message=error_message,
                details=details
            )
        
        logger.info(
            "message_validation_passed",
            current_tokens=current_tokens,
            projected_tokens=projected_tokens,
            percentage=percentage * 100,
            request_size_mb=request_size / (1024 * 1024)
        )
        
        return ValidationResult(
            can_send=True,
            error_message=None,
            details=details
        )
    
    def should_block_input(self, messages: List[MessageDict]) -> Tuple[bool, Optional[str]]:
        """Check if chat input should be blocked due to context being full."""
        current_tokens = self.get_current_tokens(messages)
        percentage = current_tokens / self.context_window_size
        
        if percentage >= self.HARD_LIMIT:
            reason = (
                "🛑 **Context Window Full** - This conversation has reached its maximum length. "
                "Please start a new conversation."
            )
            
            logger.info(
                "input_blocked_context_full",
                current_tokens=current_tokens,
                percentage=percentage * 100
            )
            
            return True, reason
        
        return False, None
    
    def get_context_status(self, current_tokens: int) -> ContextStatus:
        """Get context status for UI display."""
        percentage = current_tokens / self.context_window_size
        
        # Determine status based on thresholds
        if percentage < self.WARNING_THRESHOLD:
            status = ContextStatus(
                total_tokens=current_tokens,
                percentage=percentage * 100,
                can_accept_input=True,
                warning_message=None,
                color="#00aa44",
                status="ok"
            )
        
        elif percentage < self.CRITICAL_THRESHOLD:
            status = ContextStatus(
                total_tokens=current_tokens,
                percentage=percentage * 100,
                can_accept_input=True,
                warning_message=(
                    f"⚠️ Context usage at {percentage*100:.1f}%. "
                    "Consider starting a new conversation soon."
                ),
                color="#ffaa00",
                status="warning"
            )
        
        elif percentage < self.HARD_LIMIT:
            status = ContextStatus(
                total_tokens=current_tokens,
                percentage=percentage * 100,
                can_accept_input=True,
                warning_message=(
                    f"⚠️ Context usage at {percentage*100:.1f}%. "
                    "Please start a new conversation soon."
                ),
                color="#ff8800",
                status="critical"
            )
        
        else:
            status = ContextStatus(
                total_tokens=current_tokens,
                percentage=min(percentage * 100, 100),
                can_accept_input=False,
                warning_message=(
                    "🛑 Context window full. "
                    "You must start a new conversation."
                ),
                color="#ff0000",
                status="full"
            )
        
        logger.debug(
            "context_status_generated",
            current_tokens=current_tokens,
            percentage=percentage * 100,
            status=status.status,
            can_accept_input=status.can_accept_input
        )
        
        return status
    
# Module-level instance for easy imports
context_manager = ContextManager()

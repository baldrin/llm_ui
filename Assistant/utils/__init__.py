"""Utility modules organized by functionality."""

# CORE UTILITIES
from utils.core.id_generator import (
    generate_chat_id,
    generate_log_id,
    generate_message_id
)
from utils.core.structured_logger import (
    get_logger,
    setup_structured_logging,
    LogContext,
    OperationLogger
)
from utils.core.session_utils import (
    get_user_info,
    get_request_info,
    initialize_session_tracking,
    cleanup_chat_cache
)

# CONTENT
from utils.content.token_calculator import (
    token_calculator, 
    TokenCalculator
)
from utils.content.pdf_handler import (
    pdf_handler,
    PDFHandler
)
from utils.content.image_encoder import (
    get_encoder,
    estimate_image_size,
    estimate_images_total_size,
    encode_image
)
from utils.content.file_handler import (
    process_uploaded_file,
    format_file_content,
    is_image_file,
    is_pdf_file
)
from utils.content.image_utils import (
    calculate_resized_dimensions,
    get_image_dimensions_for_encoding
)

# CACHING
from utils.caching.cache_utils import (
    invalidate_message_cache,
    invalidate_context_cache,
    invalidate_chat_caches,
    get_cached_tokens
)
from utils.caching.ownership_cache import (
    is_ownership_cached,
    cache_ownership,
    invalidate_ownership_cache,
    verify_ownership_with_cache
)

# MONITORING
from utils.monitoring.performance_monitor import (
    performance_monitor, 
    PerformanceMonitor
)
from utils.monitoring.system_monitor import (
    system_monitor,
    SystemMonitor
)

# CHAT
from utils.chat.chat_utils import (
    get_chat_title
)
from utils.chat.context_manager import (
    context_manager,
    ContextManager
)
from utils.chat.prompt_loader import (
    prompt_loader,
    load_prompt,
    get_system_prompt,
    get_title_generation_prompt
)

# UI
from utils.ui.loading_states import (
    show_conversation_skeleton,
    show_loading_spinner,
    show_chat_list_skeleton,
    LoadingContext
)
from utils.ui.ui_helpers import (
    hide_streamlit_ui,
    get_base64_of_image
)

__all__ = [
    # Core
    'generate_chat_id',
    'generate_log_id',
    'generate_message_id',
    'get_logger',
    'setup_structured_logging',
    'LogContext',
    'OperationLogger',
    'get_user_info',
    'get_request_info',
    'initialize_session_tracking',
    'cleanup_chat_cache',
    # Content
    'token_calculator',
    'TokenCalculator',
    'pdf_handler',
    'PDFHandler',
    'get_encoder',
    'estimate_image_size',
    'estimate_images_total_size',
    'encode_image',
    'process_uploaded_file',
    'format_file_content',
    'is_image_file',
    'is_pdf_file',
    'calculate_resized_dimensions',
    'get_image_dimensions_for_encoding',
    # Caching
    'invalidate_message_cache',
    'invalidate_context_cache',
    'invalidate_chat_caches',
    'get_cached_tokens',
    'is_ownership_cached',
    'cache_ownership',
    'invalidate_ownership_cache',
    'verify_ownership_with_cache',
    # Monitoring
    'performance_monitor',
    'PerformanceMonitor',
    'system_monitor',
    'SystemMonitor',
    # Chat
    'get_chat_title',
    'context_manager',
    'ContextManager',
    'prompt_loader',
    'load_prompt',
    'get_system_prompt',
    'get_title_generation_prompt',
    # UI
    'show_conversation_skeleton',
    'show_loading_spinner',
    'show_chat_list_skeleton',
    'LoadingContext',
    'hide_streamlit_ui',
    'get_base64_of_image',
]
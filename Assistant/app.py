"""
Main Streamlit application for Developer Assistant.
"""
import streamlit as st
from dotenv import load_dotenv
import logging
from datetime import datetime
from typing import Dict, List
import time

from utils.ui.ui_helpers import hide_streamlit_ui, get_base64_of_image
from utils.core.id_generator import generate_chat_id
from utils.core.session_utils import (
    get_user_info, 
    initialize_session_tracking
)

from config.constants import DEFAULT_CHAT_TITLE

# Service layer
from services.llm_service import LLMService
from services.db_service import get_db_service
from services.db_logger import get_db_logger

# UI components
from components.sidebar import render_sidebar
from components.chat_window import render_chat_window
from components.input_area import render_input_area
from components.llm_response_handler import handle_llm_response

from config.config_loader import config 

from config.exceptions import (
    DeveloperAssistantError,
    ConfigurationError,
    AuthenticationError,
    ServiceUnavailableError
)

from utils.core.structured_logger import get_logger, setup_structured_logging

from config.types import ChatDict

load_dotenv()

st.set_page_config(
    layout="wide",
    page_title=config.get('app.page_title'),
    page_icon=config.get('app.icon'),
)

# Hide default Streamlit UI elements
hide_streamlit_ui()

setup_structured_logging()

log_level_name = (
    config.get('logging.log_level') or "INFO"
).upper()

try:
    log_level = getattr(logging, log_level_name)
except AttributeError:
    log_level = logging.INFO
    print(
        f"Warning: Invalid log level '{log_level_name}', "
        f"using INFO as fallback"
    )

logging.getLogger().setLevel(log_level)

# Suppress noisy external loggers
for logger_name in config.get('logging.suppress_noisy_loggers', []):
    logging.getLogger(logger_name).setLevel(logging.WARNING)
    logging.getLogger(logger_name).propagate = False

logger = get_logger(__name__)

def validate_environment() -> None:
    """Validate required environment variables are present."""
    
    missing_vars = config.validate_environment_variables()

    if missing_vars:
        error_msg = (
            "Missing or invalid environment variables:\n  - " + 
            "\n  - ".join(missing_vars)
        )
        st.error("**Configuration Error**")
        st.error(error_msg)
        st.error(
            "Please check your app.yaml configuration and environment variables."
        )

        # Show debug info in side in dev environement
        if config.is_development():
            with st.expander("🔍 Debug Information"):
                st.json(config.get_environment_info())

        st.stop()

    logger.debug("environment_validation_passed")

def initialize_session_state() -> None:
    """Initialize all session state variables."""
    logger.debug("session_state_initializing")

    if "current_time" not in st.session_state:
        st.session_state.current_time = datetime.now()

    if "session_id" not in st.session_state:
        session_id = initialize_session_tracking()
        logger.info("session_tracking_initialized", session_id=session_id)

    if "user_info" not in st.session_state:
        try:
            st.session_state.user_info = get_user_info()
            logger.info(
                "session_initialized_for_user",
                user_id=st.session_state.user_info.get('user_id'),
                session_id=st.session_state.session_id
            )
        except AuthenticationError as e:
            st.error("**Authentication Error**")
            st.error(f"{e.message}")
            if e.details:
                st.json(e.details)
            st.stop()

    if "chat_ownership_cache" not in st.session_state:
        st.session_state.chat_ownership_cache = {}
        logger.debug("chat_ownership_cache_initialized")

    if "pdf_metadata_cache" not in st.session_state:
        st.session_state.pdf_metadata_cache = {}
        logger.debug("pdf_metadata_cache_initialized")

    if "chat_service" not in st.session_state:
        try:
            logger.debug("creating_db_service")
            st.session_state.chat_service = get_db_service()
        except Exception as e:
            logger.error("db_service_init_failed", error=str(e))
            st.error("**Service Initialization Error**")
            st.error(
                "Failed to initialize database service. "
                "Please try refreshing the page."
            )
            if config.is_development():
                st.exception(e)
            st.stop()

    if "db_logger" not in st.session_state:
        try:
            logger.debug("creating_db_logger")
            st.session_state.db_logger = get_db_logger()
        except Exception as e:
            logger.error("db_logger_init_failed", error=str(e))
            st.warning("Activity logging unavailable")

    if "llm_service" not in st.session_state:
        try:
            logger.debug("creating_llm_service")
            st.session_state.llm_service = LLMService()
        except Exception as e:
            logger.error("llm_service_init_failed", error=str(e))
            st.error("⚠️ **Service Initialization Error**")
            st.error(
                "Failed to initialize AI service. "
                "Please check your configuration."
            )
            if config.is_development():
                st.exception(e)
            st.stop()

    # UI control flags
    if "needs_rerun" not in st.session_state: 
        st.session_state.needs_rerun = False

    if "is_generating" not in st.session_state: 
        st.session_state.is_generating = False

    # Streaming control flag
    if "stop_streaming" not in st.session_state:
        st.session_state.stop_streaming = False

    logger.debug("session_state_initialization_complete")

def initialize_llm_models() -> Dict[str, str]:
    """Initialize available LLM models and selection."""
    # Get models as list of dicts from config
    llm_models_list: List[Dict[str, str]] = config.get('llm.llm_models', [])
    
    # Convert to map format: {name: id}
    available_llms_map: Dict[str, str] = {
        model['name']: model['id'] 
        for model in llm_models_list
    }
    
    available_llms_list = list(available_llms_map.keys())

    if "selected_llm" not in st.session_state:
        if available_llms_list:
            st.session_state.selected_llm = available_llms_list[0]
        else:
            st.session_state.selected_llm = "None"
    elif (st.session_state.selected_llm not in available_llms_list and 
          st.session_state.selected_llm != "None"):
        st.session_state.selected_llm = (
            available_llms_list[0] if available_llms_list else "None"
        )

    return available_llms_map

def initialize_chats() -> None:
    """
    Initialize chat history with database persistence and lazy loading.
    Creates a fresh conversation on first visit to encourage token efficiency.
    """
    if "chats" in st.session_state:
        return

    from threading import Lock

    try:
        if "_chats_init_lock" not in st.session_state:
            st.session_state._chats_init_lock = Lock()
    except Exception as e:
        logger.error("Error creating initialization lock", error=str(e))
    
    lock = st.session_state.get("_chats_init_lock")
    if lock:
        with lock:
            if "chats" in st.session_state:
                return

            _load_or_create_chats()
    else:
        if "chats" not in st.session_state:
            _load_or_create_chats()


def _load_or_create_chats() -> None:
    """Helper function with optional pre-loading."""
    user_id = st.session_state.user_info.get("user_id")

    from utils.ui.loading_states import LoadingContext

    with LoadingContext(
        message="Loading your chat history",
        icon="📚",
        show_skeleton=False
    ):
        start_time = time.time()

        try:
            loaded_chats: Dict[str, ChatDict] = st.session_state.chat_service.load_user_chats(user_id)

            load_duration = time.time() - start_time

            if load_duration > 0.5:
                logger.warning("slow_chat_list_load", duration_ms=load_duration * 1000, chat_count=len(loaded_chats))

            preload_count = config.get('app.preload_recent_chats', 0)
            if preload_count > 0 and loaded_chats:
                chat_ids_to_preload = list(loaded_chats.keys())[:preload_count]

                for chat_id in chat_ids_to_preload:
                    try:
                        messages = st.session_state.chat_service.load_conversation_messages(user_id, chat_id)
                        loaded_chats[chat_id]["messages"] = messages
                        loaded_chats[chat_id]["loaded_at"] = datetime.now()
                        logger.debug("chat_preloaded", chat_id=chat_id, message_count=len(messages))
                    except Exception as e:
                        logger.warning("preload_failed", chat_id=chat_id, error=str(e))

            create_fresh = config.get('app.create_fresh_chat_on_visit', True)

            if create_fresh:
                fresh_chat_id = generate_chat_id()
                fresh_chat: ChatDict = {
                    "title": DEFAULT_CHAT_TITLE,
                    "messages": [],
                    "created_at": None,
                    "updated_at": None,
                    "message_count": 0,
                    "loaded_at": None
                }

                all_chats: Dict[str, ChatDict] = {fresh_chat_id: fresh_chat}
                all_chats.update(loaded_chats)

                st.session_state.chats = all_chats
                st.session_state.current_chat_id = fresh_chat_id

                logger.info("chats_initialized_with_fresh", user_id=user_id, existing_chats=len(loaded_chats), fresh_chat_id=fresh_chat_id, preloaded=preload_count)
            else:
                if loaded_chats:
                    st.session_state.chats = loaded_chats
                    st.session_state.current_chat_id = list(loaded_chats.keys())[0]
                    logger.info("chats_loaded_without_fresh", user_id=user_id, chat_count=len(loaded_chats))
                else:
                    _create_default_chat(user_id)

        except Exception as e:
            logger.error("chat_history_load_failed", error=str(e), user_id=user_id)
            _create_default_chat(user_id)


def _create_default_chat(user_id: str) -> None:
    """Create a default chat with error handling."""
    try:
        first_chat_id = generate_chat_id()
        default_chat = {
            first_chat_id: {
                "title": DEFAULT_CHAT_TITLE,
                "messages": [],
                "created_at": None,
                "updated_at": None,
                "message_count": 0,
                "loaded_at": None
            }
        }

        st.session_state.chats = default_chat
        st.session_state.current_chat_id = first_chat_id
        logger.info("Created default chat for user", user_id=user_id)

    except Exception as e:
        logger.error("Error creating default chat", error=str(e))
        
        st.session_state.chats = {}
        st.session_state.current_chat_id = None


def handle_pending_operations() -> None:
    """Handle any pending async operations with error handling."""
    # Handle pending chat deletion
    if "pending_delete_chat_id" in st.session_state:
        chat_id: str = st.session_state.pending_delete_chat_id

        try:
            del st.session_state.pending_delete_chat_id
        except Exception as e:
            logger.error(
                "pending_delete_removal_failed",
                error=str(e)
            )

        try:
            user_id = st.session_state.user_info.get("user_id")
            if user_id:
                st.session_state.chat_service.soft_delete_chat(
                    user_id,
                    chat_id
                )

            # Get current chat BEFORE deletion
            was_current_chat = (chat_id == st.session_state.current_chat_id)

            # Find chat index BEFORE deletion
            chat_ids = list(st.session_state.chats.keys())
            try:
                delete_index = chat_ids.index(chat_id)
            except ValueError:
                delete_index = -1

            # Remove from session state
            try:
                if chat_id in st.session_state.chats:
                    del st.session_state.chats[chat_id]
            except Exception as e:
                logger.error(
                    "chat_removal_failed",
                    error=str(e),
                    chat_id=chat_id
                )

            # Determine next chat to focus
            if was_current_chat:
                # We deleted the current chat - need to pick a new one
                remaining_chats = list(st.session_state.chats.keys())

                if remaining_chats:
                    # Try to stay at same position, or go to first chat
                    if delete_index >= 0 and delete_index < len(remaining_chats):
                        # Stay at same position (next chat moved into this spot)
                        st.session_state.current_chat_id = (
                            remaining_chats[delete_index]
                        )
                    else:
                        # Deleted last chat, go to first (top) chat
                        st.session_state.current_chat_id = remaining_chats[0]

                    logger.info(
                        "chat_deleted_switched_focus",
                        deleted_chat_id=chat_id,
                        new_chat_id=st.session_state.current_chat_id,
                        was_current=True
                    )
                else:
                    # No chats left, create new one
                    new_chat_id = generate_chat_id()
                    st.session_state.chats[new_chat_id] = {
                        "title": DEFAULT_CHAT_TITLE, 
                        "messages": [],
                        "created_at": None,
                        "updated_at": None,
                        "message_count": 0,
                        "loaded_at": None
                    }
                    st.session_state.current_chat_id = new_chat_id

                    logger.info(
                        "chat_deleted_created_new",
                        deleted_chat_id=chat_id,
                        new_chat_id=new_chat_id
                    )
            else:
                # We deleted a different chat - stay on current chat
                logger.info(
                    "chat_deleted_kept_focus",
                    deleted_chat_id=chat_id,
                    current_chat_id=st.session_state.current_chat_id,
                    was_current=False
                )

            st.toast("Chat deleted successfully!", icon="🗑️")

        except Exception as e:
            logger.error(
                "chat_deletion_failed",
                error=str(e),
                chat_id=chat_id
            )
            st.toast("Error deleting chat.", icon="❌")


def render_header() -> None:
    """Render the app header with logo."""
    svg_path: str = config.get('app.icon')
    svg_base64: str = get_base64_of_image(svg_path)

    col1, col2 = st.columns([10, 1])
    with col1:
        st.markdown(
            f"""
            <div style="display: flex; align-items: center;">
                <div style="margin-right: 15px;">
                    <img src="data:image/svg+xml;base64,{svg_base64}" width="50" height="50">
                </div>
                <div style="font-size: 2.5rem; font-weight: 700; color: #1e73be;">
                    {config.get('app.title')}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )    
    with col2:
        st.empty()


def main() -> None:
    """Main application function with comprehensive error handling."""

    try:
        validate_environment()
        initialize_session_state()
        available_llms_map = initialize_llm_models()
        initialize_chats()

        render_header()
        render_sidebar()
        render_chat_window()
        render_input_area()

        handle_llm_response(available_llms_map)

        handle_pending_operations()

        # Single rerun point instead of st.rerun() everywhere. Fixes a lot of UI rendering issues. 
        if st.session_state.needs_rerun:
            st.session_state.needs_rerun = False
            st.rerun()

    except ConfigurationError as e:
        st.error("**Configuration Error**")
        st.error(f"{e.message}")
        if e.details:
            with st.expander("Error Details"):
                st.json(e.details)
        st.stop()

    except AuthenticationError as e:
        st.error("**Authentication Error**")
        st.error(f"{e.message}")
        if e.details:
            with st.expander("Error Details"):
                st.json(e.details)
        st.stop()

    except ServiceUnavailableError as e:
        st.error("**Service Unavailable**")
        st.error(f"{e.message}")
        st.info("The service is temporarily unavailable. Please try again in a few moments.")
        if e.details:
            with st.expander("Error Details"):
                st.json(e.details)
        st.stop()

    except DeveloperAssistantError as e:
        st.error("**Application Error**")
        st.error(f"{e.message}")
        if e.details:
            with st.expander("Error Details"):
                st.json(e.details)

        # In development, show full trace
        if config.is_development():
            st.exception(e)
        st.stop()

    except Exception as e:
        logger.error(
            f"Unexpected error in main: {e}",
            exc_info=True
        )
        st.error("**Unexpected Error**")
        st.error("An unexpected error occurred. Please try refreshing the page.")

        # In dev, show full error
        if config.is_development():
            st.exception(e)
        else:
            st.error(f"Error: {str(e)}")
        st.stop()


if __name__ == "__main__":
    main()
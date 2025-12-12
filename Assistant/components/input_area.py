import streamlit as st
import html

from config.constants import CHAT_INPUT_PLACEHOLDER
from utils.core.structured_logger import get_logger
from utils.core.session_utils import get_request_info
from utils.caching.cache_utils import invalidate_chat_caches
from utils.chat.context_manager import context_manager
from services.message_processor import message_processor

logger = get_logger(__name__)

def sanitize_user_input(text: str) -> str:
    """Escape HTML/markdown characters in user input."""
    return html.escape(text)

def render_copy_button_for_rejected_message(message_content: str, button_key: str) -> None:
    """Render a copy button for rejected message content."""

    st.code(message_content, language=None)
    st.markdown("**Your message (click the copy icon in the top-right):**")

def clear_file_uploader() -> None:
    """Clear the file uploader and pending attachments."""
    # Clear pending attachments
    if "pending_attachments" in st.session_state:
        del st.session_state.pending_attachments

    # Force file uploader reset by incrementing its key counter
    if "file_uploader_key_counter" not in st.session_state:
        st.session_state.file_uploader_key_counter = 0

    st.session_state.file_uploader_key_counter += 1

    # Clear any existing file uploader state
    current_chat_id = st.session_state.get('current_chat_id')

    # Clear all possible uploader keys
    keys_to_remove = []
    for key in st.session_state.keys():
        if key.startswith(f"sidebar_file_uploader_{current_chat_id}"):
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del st.session_state[key]

    logger.debug("file_uploader_cleared_with_enhanced_cleanup", keys_removed=len(keys_to_remove))

def render_input_area() -> None:
    """Render the user input area for chat conversation with file upload support."""

    current_chat_id = st.session_state.get('current_chat_id')

    if not current_chat_id or current_chat_id not in st.session_state.chats:
        st.error("❌ No active conversation found. Please refresh the page.")
        return

    chat = st.session_state.chats[current_chat_id]
    messages = chat.get('messages', [])

    should_block, block_reason = context_manager.should_block_input(messages)

    if should_block:
        st.error(block_reason)

        # Show "New Chat" button
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button(
                "➕ Start New Conversation",
                key="new_chat_from_blocked_input",
                type="primary",
                use_container_width=True
            ):
                create_new_chat_and_clear()
                st.session_state.needs_rerun = True

    prompt = st.chat_input(
        CHAT_INPUT_PLACEHOLDER, 
        disabled=st.session_state.is_generating
    )

    if prompt:
        if should_block:
            st.error("Cannot send message, the context window is full. Please start a new conversation")
            return

        process_user_input(prompt)


def process_user_input(prompt: str) -> None:
    """Process user input with consolidated validation."""

    current_chat_id = st.session_state.get('current_chat_id')

    if not current_chat_id or current_chat_id not in st.session_state.chats:
        st.error("❌ No active conversation found. Please refresh the page.")
        return

    chat = st.session_state.chats[current_chat_id]
    messages = chat.get('messages', [])

    # Get any pending attachments
    attachments = st.session_state.get("pending_attachments", {
        'text_files': [],
        'images': [],
        'pdfs': []
    })

    validation = context_manager.validate_can_send(
        messages=messages,
        new_message=prompt,
        attachments=attachments if has_attachments(attachments) else None
    )

    if not validation.can_send:
        # Show the message in a copyable code block
        render_copy_button_for_rejected_message(prompt, "rejected_message_copy")

        # Show error with details
        st.error(validation.error_message)

        # Show "Start New Conversation" button
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button(
                "➕ Start New Conversation",
                key="new_chat_from_rejected_message",
                type="primary",
                use_container_width=True
            ):
                create_new_chat_and_clear()
                st.session_state.needs_rerun = True

        # Log the rejection
        logger.warning(
            "message_rejected",
            reason=validation.details.get('reason'),
            block_type=validation.details.get('block_type'),
            details=validation.details
        )

        return

    # Reset stop flags at the START of new input
    try:
        st.session_state.stop_streaming = False
        if "save_partial_on_stop" in st.session_state:
            del st.session_state.save_partial_on_stop
        if "_streaming_partial_response" in st.session_state:
            del st.session_state._streaming_partial_response
        logger.debug("stop_flags_reset", value=False)
    except Exception as e:
        logger.error("stop_flags_reset_failed", error=str(e))

    # Use message processor to build message content with clean indicators
    message_content = message_processor.build_user_message_content(prompt, attachments)

    try:
        user_message = {"role": "user", "content": message_content}

        # Store attachments separately for LLM processing (all attachment types)
        if has_attachments(attachments):
            user_message["attachments"] = {
                "text_files": attachments.get('text_files', []),
                "images": [img['image'] for img in attachments.get('images', [])],
                "pdfs": [pdf['bytes'] for pdf in attachments.get('pdfs', [])]
            }

        st.session_state.chats[current_chat_id]["messages"].append(user_message)

        logger.info(
            "message_accepted",
            validation_details=validation.details,
            has_attachments=has_attachments(attachments)
        )

    except Exception as e:
        logger.error("message_append_failed", error=str(e))
        st.error("Failed to add message to conversation. Please try again.")
        return

    try:
        user_info = st.session_state.user_info
        request_info = get_request_info()

        message_id = st.session_state.chat_service.save_message(
            user_id=user_info.get("user_id"),
            chat_id=current_chat_id,
            role="user",
            content=message_content,
            llm_model=st.session_state.selected_llm
        )

        st.session_state.db_logger.log_message(
            user_id=user_info.get("user_id"),
            message_id=message_id,
            message_type="user",
            chat_id=current_chat_id,
            selected_llm=st.session_state.selected_llm,
            input_tokens=0,
            output_tokens=0,
            user_name=user_info.get("user_name"),
            user_email=user_info.get("user_email"),
            session_id=st.session_state.session_id,
            ip_address=request_info.get("ip_address"),
            user_agent=request_info.get("user_agent")
        )

        # Invalidate caches
        invalidate_chat_caches(current_chat_id)

    except Exception as e:
        logger.error("message_save_failed", error=str(e))
        st.warning("Message displayed but may not be saved to database.")

    # Display user message immediately using message processor for clean display
    with st.chat_message("user"):
        #display_content = message_processor.format_message_for_display(user_message)
        st.text(user_message)

    # Clear pending attachments and file uploader
    clear_file_uploader()

    # Set the flag and force immediate rerun
    try:
        st.session_state.is_generating = True
        logger.info("is_generating_flag_set", value=True, chat_id=current_chat_id)

        # CRITICAL: Force rerun so UI updates BEFORE generation starts
        st.rerun()

    except Exception as e:
        logger.error("is_generating_flag_failed", error=str(e))
        st.error("Failed to start response generation. Please try again.")

def create_new_chat_and_clear() -> None:
    """Helper to create new chat and clear all state."""
    from utils.core.id_generator import generate_chat_id
    from config.constants import DEFAULT_CHAT_TITLE

    # Create new chat
    new_chat_id = generate_chat_id()
    new_chat_data = {
        "title": DEFAULT_CHAT_TITLE,
        "messages": [],
        "created_at": None,
        "updated_at": None,
        "message_count": 0,
        "loaded_at": None
    }

    # Add to beginning of chats
    new_chats_dict = {new_chat_id: new_chat_data}
    new_chats_dict.update(st.session_state.chats)

    st.session_state.chats = new_chats_dict
    st.session_state.current_chat_id = new_chat_id
    st.session_state.is_generating = False

    # Clear file uploader
    clear_file_uploader()

    # Clear any pending messages
    if "pending_user_message" in st.session_state:
        del st.session_state.pending_user_message
    if "request_size_exceeded" in st.session_state:
        del st.session_state.request_size_exceeded

    logger.info("new_chat_created_and_cleared", chat_id=new_chat_id)

# Helper function at top of file
def has_attachments(attachments: dict) -> bool:
    """Check if attachments dict has any actual attachments."""
    return bool(
        attachments.get('text_files') or 
        attachments.get('images') or 
        attachments.get('pdfs')
    )
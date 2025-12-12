import streamlit as st
from typing import List, Any
from datetime import datetime
import streamlit.components.v1 as components

from config.config_loader import config
from config.types import MessageDict
from utils.core.structured_logger import get_logger, OperationLogger
from services.message_processor import message_processor

logger = get_logger(__name__)


def load_messages_for_chat(user_id: str, chat_id: str, _service: Any) -> List[MessageDict]:
    """
    Load messages with smart session-based caching.
    Only hits DB once per chat per session.
    """
    if chat_id in st.session_state.chats:
        chat = st.session_state.chats[chat_id]
        if chat.get("messages") is not None:
            logger.debug("messages_from_memory", chat_id=chat_id, message_count=len(chat["messages"]))
            return chat["messages"]

    op_logger = OperationLogger("load_messages_for_chat")

    with op_logger.track(user_id=user_id, chat_id=chat_id):
        messages = _service.load_conversation_messages(user_id, chat_id)
        logger.info("messages_loaded_from_db", user_id=user_id, chat_id=chat_id, message_count=len(messages))
        return messages


def ensure_current_chat_loaded() -> None:
    """Ensure messages for current chat are loaded before rendering."""
    if st.session_state.current_chat_id not in st.session_state.chats:
        logger.warning("current_chat_not_found", chat_id=st.session_state.current_chat_id)
        return

    chat = st.session_state.chats[st.session_state.current_chat_id]

    if chat.get("messages") is None:
        from utils.ui.loading_states import LoadingContext

        with LoadContext(user_id=st.session_state.user_info.get("user_id")):
            with LoadingContext(message="Loading conversation", icon="💬", show_skeleton=True, skeleton_type="conversation", skeleton_count=3):
                try:
                    user_id = st.session_state.user_info.get("user_id")
                    messages = load_messages_for_chat(user_id, st.session_state.current_chat_id, st.session_state.chat_service)
                    chat["messages"] = messages
                    chat["loaded_at"] = datetime.now()
                    logger.info("chat_loaded", user_id=user_id, chat_id=st.session_state.current_chat_id, message_count=len(messages))
                except Exception as e:
                    logger.error("chat_load_failed", user_id=user_id, chat_id=st.session_state.current_chat_id, error=str(e))
                    chat["messages"] = []


def render_copy_button(text_to_copy: str, button_key: str) -> None:
    """Render a copy button using Streamlit components."""
    import html

    # Escape the text properly
    safe_text = html.escape(text_to_copy, quote=True)

    # Create the HTML component
    button_html = f"""
    <div style="margin-top: 10px;">
        <textarea id="text_{button_key}" style="position: absolute; left: -9999px;" readonly>{safe_text}</textarea>
        <button 
            id="btn_{button_key}" 
            onclick="copyText_{button_key}()"
            style="
                padding: 6px 12px;
                font-size: 14px;
                border-radius: 6px;
                background-color: #ffffff;
                border: 1px solid #d0d0d0;
                cursor: pointer;
                font-family: 'Source Sans Pro', sans-serif;
                color: #333;
                transition: all 0.3s;
            "
            onmouseover="this.style.backgroundColor='#f0f0f0'"
            onmouseout="this.style.backgroundColor='#ffffff'"
        >📋</button>
    </div>

    <script>
        function copyText_{button_key}() {{
            const text = document.getElementById('text_{button_key}');
            const btn = document.getElementById('btn_{button_key}');

            text.select();
            text.setSelectionRange(0, 99999);

            try {{
                document.execCommand('copy');
                btn.textContent = '✅ Copied!';
                btn.style.backgroundColor = '#4CAF50';
                btn.style.color = 'white';

                setTimeout(function() {{
                    btn.textContent = '📋';
                    btn.style.backgroundColor = '#ffffff';
                    btn.style.color = '#333';
                }}, 2000);
            }} catch (err) {{
                btn.textContent = '❌ Failed';
                setTimeout(function() {{
                    btn.textContent = '📋';
                }}, 2000);
            }}
        }}
    </script>
    """
    components.html(button_html, height=60)


@st.fragment
def render_messages_fragment(messages: List[MessageDict]) -> None:
    """Render messages with copy functionality and pagination."""
    max_initial_messages = config.get('app.max_initial_messages', 10)

    if len(messages) > max_initial_messages:
        show_all_key = f"show_all_{st.session_state.current_chat_id}"
        if show_all_key not in st.session_state:
            st.session_state[show_all_key] = False

        if not st.session_state[show_all_key]:
            if st.button(f"📜 Load {len(messages) - max_initial_messages} older messages", key=f"load_more_{st.session_state.current_chat_id}"):
                st.session_state[show_all_key] = True
                st.session_state.needs_rerun = True
            messages_to_show = messages[-max_initial_messages:]
            st.info(f"Showing last {max_initial_messages} of {len(messages)} messages")
        else:
            messages_to_show = messages
    else:
        messages_to_show = messages

    for idx, msg in enumerate(messages_to_show):
        with st.chat_message(msg["role"]):
            # Use message processor for clean display formatting
            #display_content = message_processor.format_message_for_display(msg)
            content = msg.get("content", "")

            # Render message content based on role
            if msg["role"] == "assistant":
                st.markdown(content, unsafe_allow_html=True)
            else:
                # For user messages, show content as text
                st.text(content)

                # Show attached files if they exist
                if "attachments" in msg:
                    attachments = msg["attachments"]

                    # Show text files in expandable sections
                    if attachments.get("text_files"):
                        st.markdown("**📄 Attached Text Files:**")
                        for text_file in attachments["text_files"]:
                            with st.expander(f"📎 {text_file['name']}"):
                                st.text(text_file['content'])

                    # Show image file names (images themselves are processed by LLM)
                    if attachments.get("images"):
                        image_count = len(attachments["images"])
                        st.caption(f"🖼️ {image_count} image(s) attached to this message")

                    # Show PDF file info (PDFs themselves are processed by LLM)
                    if attachments.get("pdfs"):
                        pdf_count = len(attachments["pdfs"])
                        st.caption(f"📄 {pdf_count} PDF(s) attached to this message")

            # Show stopped indicator if applicable
            if msg.get("was_stopped"):
                st.caption("⚠️ Generation stopped by user")

            # Copy button for assistant messages
            if msg["role"] == "assistant":
                render_copy_button(msg["content"], f"copy_{idx}")


def render_chat_window() -> None:
    """Render the chat conversation window with optimized loading."""
    chat_container = st.container()

    with chat_container:
        if st.session_state.current_chat_id in st.session_state.chats:
            chat = st.session_state.chats[st.session_state.current_chat_id]
            messages = chat.get("messages")

            if messages is None:
                ensure_current_chat_loaded()
                messages = chat.get("messages", [])

            if messages:
                render_messages_fragment(messages)
        else:
            logger.warning("chat_not_found", chat_id=st.session_state.current_chat_id)
            st.warning("Selected conversation not found. Please select another conversation or start a new one.")
            if st.session_state.chats:
                st.session_state.current_chat_id = list(st.session_state.chats.keys())[-1]


class LoadContext:
    """Context manager for structured logging context."""
    def __init__(self, **context: Any):
        self.context = context
    def __enter__(self) -> 'LoadContext':
        return self
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass
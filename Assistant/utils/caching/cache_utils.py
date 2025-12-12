from typing import List, Tuple, Optional
from datetime import datetime
import streamlit as st

from config.types import MessageDict
from utils.core.structured_logger import get_logger

logger = get_logger(__name__)


def invalidate_message_cache(chat_id: str) -> None:
    """
    Invalidate message pagination cache for a chat.
    Call this when messages are added/removed.
    """
    show_all_key = f"show_all_{chat_id}"
    if show_all_key in st.session_state:
        del st.session_state[show_all_key]
        logger.debug("pagination_state_cleared", chat_id=chat_id)


def invalidate_context_cache(chat_id: str) -> None:
    """
    Invalidate cached token count for a chat.
    Call this when messages are added/removed.
    """
    cache_key = f'_cached_tokens_{chat_id}'
    if cache_key in st.session_state:
        del st.session_state[cache_key]
        logger.debug("token_cache_invalidated", chat_id=chat_id)


def invalidate_chat_caches(chat_id: str) -> None:
    """
    Invalidate ALL caches for a chat.
    Call this when messages are added/removed.
    """
    invalidate_message_cache(chat_id)
    invalidate_context_cache(chat_id)
    logger.debug("all_caches_invalidated", chat_id=chat_id)


def get_cached_tokens(
    chat_id: str, 
    messages: Optional[List[MessageDict]]
) -> Tuple[int, bool]:
    """Get token count with caching and lazy loading."""
    from utils.chat.context_manager import context_manager

    cache_key = f'_cached_tokens_{chat_id}'

    # Check cache first
    if cache_key in st.session_state:
        tokens = st.session_state[cache_key]
        logger.debug("context_tokens_from_cache", tokens=tokens)
        return tokens, False

    # Messages not loaded yet
    if messages is None:
        logger.debug("messages_not_loaded_for_context", chat_id=chat_id)

        try:
            user_id = st.session_state.user_info.get("user_id")
            messages = st.session_state.chat_service.load_conversation_messages(
                user_id,
                chat_id
            )

            # Update chat with loaded messages
            if chat_id in st.session_state.chats:
                st.session_state.chats[chat_id]["messages"] = messages
                st.session_state.chats[chat_id]["loaded_at"] = datetime.now()

            # Calculate and cache
            tokens = context_manager.get_current_tokens(messages)
            st.session_state[cache_key] = tokens

            logger.info(
                "messages_loaded_for_context",
                chat_id=chat_id,
                message_count=len(messages),
                tokens=tokens
            )

            return tokens, False

        except Exception as e:
            logger.error(
                "context_messages_load_failed",
                error=str(e),
                chat_id=chat_id
            )
            return 0, False

    # Messages loaded, calculate and cache
    tokens = context_manager.get_current_tokens(messages)
    st.session_state[cache_key] = tokens
    logger.debug("context_tokens_calculated", tokens=tokens)

    return tokens, False
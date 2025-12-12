"""
Chat ownership caching utilities.
Reduces database queries by caching ownership verification results.
"""
import streamlit as st
from typing import Optional
from utils.core.structured_logger import get_logger

logger = get_logger(__name__)

def get_cache_key(chat_id: str, user_id: str) -> str:
    """ Generate cache key for ownership check. """
    return f"{chat_id}:{user_id}"

def is_ownership_cached(chat_id: str, user_id: str) -> bool:
    """ Check if ownership is already cached. """
    cache_key = get_cache_key(chat_id, user_id)
    return st.session_state.chat_ownership_cache.get(cache_key, False)

def cache_ownership(chat_id: str, user_id: str, is_owner: bool = True) -> None:
    """ Cache ownership verification result. """
    cache_key = get_cache_key(chat_id, user_id)
    st.session_state.chat_ownership_cache[cache_key] = is_owner
    
    logger.debug(
        "ownership_cached",
        chat_id=chat_id,
        user_id=user_id,
        is_owner=is_owner
    )

def invalidate_ownership_cache(chat_id: Optional[str] = None) -> None:
    """ Invalidate ownership cache. """
    if chat_id is None:
        # Clear entire cache
        count = len(st.session_state.chat_ownership_cache)
        st.session_state.chat_ownership_cache.clear()
        logger.debug("ownership_cache_cleared", entries_cleared=count)
    else:
        # Clear specific chat entries
        keys_to_remove = [
            key for key in st.session_state.chat_ownership_cache.keys()
            if key.startswith(f"{chat_id}:")
        ]
        for key in keys_to_remove:
            del st.session_state.chat_ownership_cache[key]
        logger.debug(
            "ownership_cache_invalidated",
            chat_id=chat_id,
            entries_removed=len(keys_to_remove)
        )


def verify_ownership_with_cache(chat_id: str, user_id: str) -> bool:
    """
    Verify chat ownership with caching.
    Only hits database if not cached.
    """
    from services.db_connection_manager import get_db_manager
    from config.constants import CONVERSATIONS_TABLE

    # Check cache first
    if is_ownership_cached(chat_id, user_id):
        logger.debug("ownership_verified_from_cache", chat_id=chat_id)
        return True

    # Not cached - check database
    db_manager = get_db_manager()

    with db_manager.get_connection() as connection:
        with connection.cursor() as cursor:
            verify_user_query = f"""
            SELECT user_id FROM {db_manager.catalog}.{db_manager.schema}.{CONVERSATIONS_TABLE}
            WHERE chat_id = ? AND deleted = FALSE
            LIMIT 1
            """
            cursor.execute(verify_user_query, (chat_id,))
            owner_row = cursor.fetchone()

    if owner_row is None:
        # Chat doesn't exist yet - cache as owner
        cache_ownership(chat_id, user_id, True)
        return True

    if owner_row[0] != user_id:
        # User doesn't own this chat
        logger.error(
            "cross_user_access_attempt",
            attempted_user=user_id,
            actual_owner=owner_row[0],
            chat_id=chat_id
        )
        raise PermissionError(
            f"User {user_id} attempted to access chat {chat_id} owned by {owner_row[0]}"
        )

    # User owns the chat - cache it
    cache_ownership(chat_id, user_id, True)
    return True
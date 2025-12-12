"""
Session and request information utilities.
Handles user authentication, session tracking, and request metadata.
"""
import streamlit as st
import re
from datetime import datetime
from typing import Dict, Optional
import uuid

from config.types import UserInfo
from config.exceptions import AuthenticationError
from config.config_loader import config

from utils.core.structured_logger import get_logger

logger = get_logger(__name__)


def validate_email(email: Optional[str]) -> bool:
    """Validate email format."""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_user_id(user_id: Optional[str]) -> bool:
    """Validate user_id is non-empty and reasonable length."""
    if not user_id or not isinstance(user_id, str):
        return False
    if len(user_id) < 3 or len(user_id) > 255:
        return False
    return True

def validate_user_name(user_name: Optional[str]) -> bool:
    """Validate user_name is non-empty."""
    if not user_name or not isinstance(user_name, str):
        return False
    if len(user_name.strip()) < 1:
        return False
    return True

def get_user_info() -> UserInfo:
    """Get user information from Databricks context or use local defaults with validation."""
    use_local = False
    
    try:
        headers = st.context.headers
        user_name = headers.get("X-Forwarded-Preferred-Username")
        user_email = headers.get("X-Forwarded-Email")
        user_id = headers.get("X-Forwarded-User")
        
        if not (validate_user_id(user_id) and 
                validate_user_name(user_name) and 
                validate_email(user_email)):
            
            logger.info(
                "headers_invalid_using_local",
                has_user_id=bool(user_id),
                has_user_name=bool(user_name),
                has_user_email=bool(user_email)
            )
            use_local = True
        else:
            logger.info(
                "user_authenticated_from_headers",
                user_id=user_id,
                user_name=user_name,
                user_email=user_email
            )
            
            return {
                "user_name": user_name.strip(),
                "user_email": user_email.strip().lower(),
                "user_id": user_id.strip(),
            }
        
    except Exception as e:
        logger.info("headers_not_accessible_using_local", error=str(e))
        use_local = True
    
    # Use local development values
    if use_local:
        user_name = config.get("user.name", "Local Developer")
        user_email = config.get("user.email", "local@example.com")
        user_id = config.get("user.id", "local-dev-id")
        
        if not validate_user_id(user_id):
            logger.error("invalid_local_user_id", user_id=user_id)
            raise AuthenticationError(
                "Invalid user.id in environment variables",
                details={"user_id": user_id}
            )
        
        if not validate_user_name(user_name):
            logger.error("invalid_local_user_name", user_name=user_name)
            raise AuthenticationError(
                "Invalid user.name in environment variables",
                details={"user_name": user_name}
            )
        
        if not validate_email(user_email):
            logger.error("invalid_local_user_email", user_email=user_email)
            raise AuthenticationError(
                "Invalid user.email in environment variables",
                details={"user_email": user_email}
            )
        
        logger.info(
            "local_user_authenticated",
            user_id=user_id,
            user_name=user_name,
            user_email=user_email
        )
        
        return {
            "user_name": user_name.strip(),
            "user_email": user_email.strip().lower(),
            "user_id": user_id.strip(),
        }

def get_request_info() -> Dict[str, Optional[str]]:
    """Get request information (IP address, user agent) from Streamlit context."""
    try:
        headers = st.context.headers
        
        # Try to get IP from various headers
        ip_address = (
            headers.get("X-Forwarded-For") or 
            headers.get("X-Real-IP") or 
            headers.get("Remote-Addr")
        )
        
        # Get first IP if X-Forwarded-For contains multiple
        if ip_address and "," in ip_address:
            ip_address = ip_address.split(",")[0].strip()
        
        # For local development, extract from Host header
        if not ip_address:
            host = headers.get("Host", "")
            if host.startswith("localhost") or host.startswith("127.0.0.1"):
                ip_address = "127.0.0.1"
            else:
                # Extract IP from Host if present
                ip_address = host.split(":")[0] if ":" in host else host
        
        user_agent = headers.get("User-Agent")
        
        logger.debug(
            "request_info_extracted",
            ip_address=ip_address,
            has_user_agent=bool(user_agent)
        )
        
        return {
            "ip_address": ip_address,
            "user_agent": user_agent
        }
    except Exception as e:
        logger.debug("request_info_extraction_failed", error=str(e))
        return {
            "ip_address": None,
            "user_agent": None
        }

def generate_session_id() -> str:
    """Generate a unique, human-readable session ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_suffix = str(uuid.uuid4())[:8]
    session_id = f"session_{timestamp}_{unique_suffix}"
    logger.debug("new_session_id_generated", session_id=session_id)
    return session_id

def initialize_session_tracking() -> str:
    """
    Initialize session tracking in session state.
    Creates a unique session ID if one doesn't exist.
    """
    if "session_id" not in st.session_state:
        st.session_state.session_id = generate_session_id()
        logger.info(
            "session_created",
            session_id=st.session_state.session_id
        )
    
    return st.session_state.session_id

def cleanup_chat_cache(chat_id: str) -> None:
    """Clean up all session state entries related to a chat."""
    cleanup_keys = [
        f'_cached_tokens_{chat_id}',
        f'show_all_{chat_id}',
        f'_loading_context_{chat_id}',
    ]
    
    cleaned_count = 0
    for key in cleanup_keys:
        if key in st.session_state:
            del st.session_state[key]
            cleaned_count += 1
    
    if cleaned_count > 0:
        logger.debug(
            "chat_cache_cleaned",
            chat_id=chat_id,
            keys_cleaned=cleaned_count
        )
import uuid
from datetime import datetime

def generate_chat_id() -> str:
    """Generate a unique chat ID using timestamp and UUID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_suffix = str(uuid.uuid4())[:8]
    return f"chat_{timestamp}_{unique_suffix}"


def generate_log_id() -> str:
    """Generate a unique log ID using timestamp and UUID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_suffix = str(uuid.uuid4())[:8]
    return f"log_{timestamp}_{unique_suffix}"


def generate_message_id() -> str:
    """Generate a unique message ID using timestamp and UUID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique_suffix = str(uuid.uuid4())[:8]
    return f"msg_{timestamp}_{unique_suffix}"
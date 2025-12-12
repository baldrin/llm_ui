"""
Application constants and table names.
All values pulled from configuration system with sensible defaults.
"""
from config.config_loader import config

# Database configuration
DATABASE_CATALOG = config.get('database.catalog')
DATABASE_SCHEMA = config.get('database.schema')
CONVERSATIONS_TABLE = config.get('database.conversations_table', 'conversations')
MESSAGES_TABLE = config.get('database.messages_table', 'chat_messages')
ACTIVITY_LOG_TABLE = config.get('database.activity_log_table', 'chat_activity_log')

# Message roles
USER_ROLE = "user"
ASSISTANT_ROLE = "assistant"
SYSTEM_ROLE = "system"

# Application constants
DEFAULT_CHAT_TITLE = config.get('app.default_chat_title', 'New Chat')
CHAT_INPUT_PLACEHOLDER = config.get('app.chat_input_placeholder', 'Type your message here...')

# Limits
MAX_RECENT_CHATS = config.get('app.max_recent_chats', 8)
CONTEXT_WINDOW_SIZE = config.get('llm.context_window_size', 100000)
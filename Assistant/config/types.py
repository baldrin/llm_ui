"""
Common type definitions used throughout the application.
"""
from typing import TypedDict, Optional, List, Dict, Any, Literal
from datetime import datetime

# Message role types
MessageRole = Literal["user", "assistant", "system"]

# Message type for activity logging
MessageType = Literal["user", "assistant"]


class MessageDict(TypedDict, total=False):
    """Type definition for a chat message."""
    role: MessageRole
    content: str
    created_at: Optional[datetime]
    llm_model: Optional[str]
    input_tokens: int
    output_tokens: int


class ChatDict(TypedDict, total=False):
    """Type definition for a chat conversation."""
    title: str
    messages: Optional[List[MessageDict]]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    message_count: int
    loaded_at: Optional[datetime]


class UserInfo(TypedDict):
    """Type definition for user information."""
    user_name: str
    user_email: str
    user_id: str


class DatabaseStats(TypedDict):
    """Type definition for database statistics."""
    offline_mode: bool
    database_enabled: bool
    initialized: bool
    connection_requests: int
    pool_hits: int
    pool_misses: int
    hit_rate_percent: float
    pool_size: int
    pool_available: int
    pool_in_use: int
    pool_health_percent: float
    max_connections: int
    connection_strategy: str


class ServiceStats(TypedDict):
    """Type definition for service statistics."""
    strategy: str
    queue_size: int
    worker_alive: bool
    total_operations: int
    failed_operations: int
    success_rate: float
    queuing: bool
    batching: bool
    workers: int
    initialized: bool


class PerformanceStats(TypedDict):
    """Type definition for performance statistics."""
    enabled: bool
    total_operations: int
    slow_operations: int
    slow_percentage: float
    average_time_seconds: float
    total_time_seconds: float
    slow_threshold_seconds: float
    operations: Dict[str, Dict[str, Any]]


class ContextUsage(TypedDict):
    """Type definition for context window usage."""
    tokens: int
    percentage: float
    color: str
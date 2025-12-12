"""
Async database service for chat operations.
Single worker, no batching, async for UI responsiveness.
"""
import threading
import queue
import time
import atexit
import streamlit as st
from datetime import datetime
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from services.db_connection_manager import get_db_manager

from config.constants import CONVERSATIONS_TABLE, MESSAGES_TABLE, DEFAULT_CHAT_TITLE, MAX_RECENT_CHATS
from config.config_loader import config
from config.types import ChatDict, MessageDict, MessageRole, ServiceStats
from config.exceptions import ValidationError, DatabaseError

from utils.core.id_generator import generate_message_id
from utils.monitoring.performance_monitor import performance_monitor
from utils.caching.ownership_cache import verify_ownership_with_cache, invalidate_ownership_cache
from utils.core.structured_logger import (
    get_logger, 
    OperationLogger,
    log_db_operation
)

logger = get_logger(__name__)


def validate_chat_id(chat_id: str) -> None:
    """
    Validate chat_id format.
    """
    if not chat_id or not isinstance(chat_id, str):
        raise ValidationError(
            "Invalid chat_id",
            details={"chat_id": chat_id, "type": type(chat_id).__name__}
        )
    if len(chat_id) > 255:
        raise ValidationError(
            "chat_id too long",
            details={"chat_id": chat_id, "length": len(chat_id), "max_length": 255}
        )
    if not chat_id.startswith("chat_"):
        raise ValidationError(
            "Invalid chat_id format",
            details={"chat_id": chat_id, "expected_format": "chat_YYYYMMDD_HHMMSS_xxxxxxxx"}
        )


def validate_user_id(user_id: str) -> None:
    """
    Validate user_id format.
    """
    if not user_id or not isinstance(user_id, str):
        raise ValidationError(
            "Invalid user_id",
            details={"user_id": user_id, "type": type(user_id).__name__}
        )
    if len(user_id) < 5 or len(user_id) > 255:
        raise ValidationError(
            "Invalid user_id length",
            details={"user_id": user_id, "length": len(user_id), "min_length": 5, "max_length": 255}
        )


def validate_message_content(content: str) -> None:
    """
    Validate message content.
    """
    if content is None:
        raise ValidationError("Message content cannot be None")
    if not isinstance(content, str):
        raise ValidationError(
            "Message content must be string",
            details={"type": type(content).__name__}
        )
    if len(content) > 800_000:  # 800KB limit
        raise ValidationError(
            "Message content too large",
            details={"length": len(content), "max_length": 800_000}
        )


class DBService:
    """
    Async database service - writes happen in background thread.
    Single worker, no batching, just async for UI responsiveness.
    """
    _instance: Optional['DBService'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls) -> 'DBService':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        # Prevent re-initialization with thread-safe check
        with self._lock:
            if self._initialized:
                logger.debug("db_service_already_initialized")
                return
            
            logger.info("db_service_initializing", strategy="async_single_worker")
            self._initialize()

    def _cleanup(self) -> None:
        """Graceful shutdown - wait for pending operations."""
        if self._shutdown:
            return
        
        pending = self.operation_queue.qsize()
        if pending > 0:
            timeout = config.get('database.timeouts.cleanup_timeout_seconds', 10)
            check_interval = config.get('database.timeouts.worker_check_interval_seconds', 1.0)
            
            logger.info(
                "db_service_cleanup_started",
                pending_operations=pending,
                timeout_seconds=timeout
            )
            
            start = time.time()
            
            while not self.operation_queue.empty() and (time.time() - start) < timeout:
                if not self.worker.is_alive():
                    logger.error("worker_died_during_cleanup")
                    break
                time.sleep(check_interval)
            
            remaining = self.operation_queue.qsize()
            if remaining == 0:
                logger.info("db_service_cleanup_completed", all_operations_completed=True)
            else:
                logger.warning(
                    "db_service_cleanup_timeout",
                    remaining_operations=remaining,
                    timeout_seconds=timeout
                )
        
        self._shutdown = True
        logger.info("db_service_shutdown_complete")
    
    def _worker(self) -> None:
        """Background worker that processes operations one at a time."""
        logger.debug("db_worker_started")
        
        while not self._shutdown:
            try:
                # Wait for next operation (with timeout so we can check shutdown flag)
                try:
                    operation: Dict[str, Any] = self.operation_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Process the operation
                op_type = operation.get('type')
                start_time = time.time()
                
                try:
                    if op_type == 'save_message':
                        self._save_message_to_db(operation)
                    elif op_type == 'update_title':
                        self._update_title_to_db(operation)
                    elif op_type == 'delete_chat':
                        self._delete_chat_to_db(operation)
                    else:
                        logger.warning("unknown_operation_type", operation_type=op_type)
                    
                    # Track successful operation
                    duration_ms = (time.time() - start_time) * 1000
                    with self._stats_lock:
                        self._total_operations += 1
                    
                    log_db_operation(
                        operation=op_type,
                        success=True,
                        duration_ms=duration_ms,
                        **{k: v for k, v in operation.items() if k != 'content'}  # Exclude content
                    )
                    
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    logger.error(
                        "operation_processing_failed",
                        operation_type=op_type,
                        error=str(e),
                        duration_ms=duration_ms
                    )
                    with self._stats_lock:
                        self._total_operations += 1
                        self._failed_operations += 1
                finally:
                    self.operation_queue.task_done()
                    
            except Exception as e:
                logger.error("worker_loop_error", error=str(e))
        
        logger.info("db_worker_exiting")
    
    @retry(
        stop=stop_after_attempt(config.get('database.retry.max_attempts', 3)),
        wait=wait_exponential(
            multiplier=1, 
            min=config.get('database.retry.min_wait_seconds', 1), 
            max=config.get('database.retry.max_wait_seconds', 5)
        ),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True
    )
    @performance_monitor.track_operation("save_message")
    def _save_message_to_db(self, operation: Dict[str, Any]) -> None:
        """
        Save message to database using MERGE for better performance.
        """
        op_logger = OperationLogger("save_message_to_db")

        with op_logger.track(
            message_id=operation['message_id'],
            chat_id=operation['chat_id'],
            user_id=operation['user_id'],
            role=operation['role']
        ):
            try:
                db_manager = get_db_manager()
                with db_manager.get_connection() as connection:
                    with connection.cursor() as cursor:
                        now = datetime.now()

                        # MERGE for conversation (upsert)
                        merge_conv_query = f"""
                        MERGE INTO {db_manager.catalog}.{db_manager.schema}.{CONVERSATIONS_TABLE} AS target
                        USING (
                            SELECT 
                                ? AS chat_id,
                                ? AS user_id,
                                ? AS title,
                                ? AS created_at,
                                ? AS updated_at,
                                0 AS message_count,
                                FALSE AS deleted
                        ) AS source
                        ON target.chat_id = source.chat_id 
                            AND target.user_id = source.user_id
                        WHEN MATCHED AND target.deleted = FALSE THEN
                            UPDATE SET 
                                message_count = target.message_count + 1,
                                updated_at = source.updated_at
                        WHEN NOT MATCHED THEN
                            INSERT (chat_id, user_id, title, created_at, updated_at, message_count, deleted)
                            VALUES (source.chat_id, source.user_id, source.title, source.created_at, 
                                    source.updated_at, source.message_count, source.deleted)
                        """

                        cursor.execute(merge_conv_query, (
                            operation['chat_id'],
                            operation['user_id'],
                            DEFAULT_CHAT_TITLE,
                            now,
                            now
                        ))

                        # INSERT message (messages are append-only)
                        insert_msg_query = f"""
                        INSERT INTO {db_manager.catalog}.{db_manager.schema}.{MESSAGES_TABLE}
                        (message_id, chat_id, user_id, role, content, created_at,
                        llm_model, input_tokens, output_tokens, cache_creation_input_tokens, 
                        cache_read_input_tokens, deleted)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE)
                        """

                        cursor.execute(insert_msg_query, (
                            operation['message_id'],
                            operation['chat_id'],
                            operation['user_id'],
                            operation['role'],
                            operation['content'],
                            now,
                            operation['llm_model'],
                            operation['input_tokens'],
                            operation['output_tokens'],
                            operation['cache_creation_input_tokens'],
                            operation['cache_read_input_tokens']
                        ))

                        logger.info(
                            "message_saved",
                            message_id=operation['message_id'],
                            chat_id=operation['chat_id'],
                            user_id=operation['user_id'],
                            role=operation['role']
                        )

            except ValidationError:
                raise             
            except Exception as e:
                logger.error(
                    "save_message_db_error",
                    error=str(e),
                    message_id=operation.get('message_id'),
                    chat_id=operation.get('chat_id')
                )
                raise DatabaseError(
                    "Failed to save message",
                    details={
                        "message_id": operation.get('message_id'),
                        "chat_id": operation.get('chat_id'),
                        "error": str(e)
                    }
                )
        
        
    @retry(
        stop=stop_after_attempt(config.get('database.retry.max_attempts', 3)),
        wait=wait_exponential(
            multiplier=1, 
            min=config.get('database.retry.min_wait_seconds', 1), 
            max=config.get('database.retry.max_wait_seconds', 5)
        ),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True
    )
    @performance_monitor.track_operation("update_title")
    def _update_title_to_db(self, operation: Dict[str, Any]) -> None:
        """Update title"""
        try:
            db_manager = get_db_manager()
            with db_manager.get_connection() as connection:
                with connection.cursor() as cursor:
                    query = f"""
                    UPDATE {db_manager.catalog}.{db_manager.schema}.{CONVERSATIONS_TABLE}
                    SET title = ?, updated_at = ?
                    WHERE user_id = ? AND chat_id = ?
                    """

                    cursor.execute(query, (
                        operation['title'],
                        datetime.now(),
                        operation['user_id'],
                        operation['chat_id']
                    ))

                    logger.info(
                        "title_updated",
                        chat_id=operation['chat_id'],
                        user_id=operation['user_id'],
                        new_title=operation['title']
                    )

        except Exception as e:
            logger.error("title_update_failed", error=str(e), chat_id=operation.get('chat_id'))
            raise
    
    @retry(
        stop=stop_after_attempt(config.get('database.retry.max_attempts', 3)),
        wait=wait_exponential(
            multiplier=1, 
            min=config.get('database.retry.min_wait_seconds', 1), 
            max=config.get('database.retry.max_wait_seconds', 5)
        ),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True
    )
    @performance_monitor.track_operation("delete_chat")
    def _delete_chat_to_db(self, operation: Dict[str, Any]) -> None:
        """
        Delete chat in database (called by worker).
        """
        try:
            db_manager = get_db_manager()
            with db_manager.get_connection() as connection:
                with connection.cursor() as cursor:
                    now = datetime.now()

                    # Delete conversation
                    conv_query = f"""
                    UPDATE {db_manager.catalog}.{db_manager.schema}.{CONVERSATIONS_TABLE}
                    SET deleted = TRUE, deleted_at = ?
                    WHERE user_id = ? AND chat_id = ?
                    """
                    cursor.execute(conv_query, (now, operation['user_id'], operation['chat_id']))

                    # Delete messages
                    msg_query = f"""
                    UPDATE {db_manager.catalog}.{db_manager.schema}.{MESSAGES_TABLE}
                    SET deleted = TRUE, deleted_at = ?
                    WHERE user_id = ? AND chat_id = ?
                    """
                    cursor.execute(msg_query, (now, operation['user_id'], operation['chat_id']))

                    logger.info(
                        "chat_deleted",
                        chat_id=operation['chat_id'],
                        user_id=operation['user_id']
                    )

        except Exception as e:
            logger.error(
                "chat_deletion_failed",
                error=str(e),
                chat_id=operation.get('chat_id')
            )
            raise
        
    def save_message(
        self, 
        user_id: str, 
        chat_id: str, 
        role: MessageRole, 
        content: str, 
        llm_model: Optional[str] = None, 
        input_tokens: int = 0, 
        output_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0
    ) -> str:
        """
        Queue message save operation with input validation (non-blocking, returns immediately).
        """
        # Validate inputs
        try:
            validate_user_id(user_id)
            validate_chat_id(chat_id)
            validate_message_content(content)

            if role not in ['user', 'assistant', 'system']:
                raise ValidationError(f"Invalid role: {role}", details={"role": role})

            if input_tokens < 0 or output_tokens < 0:
                raise ValidationError(
                    "Invalid token counts",
                    details={"input_tokens": input_tokens, "output_tokens": output_tokens}
                )

            verify_ownership_with_cache(chat_id, user_id)

        except ValidationError as e:
            logger.error(
                "save_message_validation_failed",
                error=str(e),
                user_id=user_id,
                chat_id=chat_id,
                role=role
            )
            raise

        message_id = generate_message_id()

        self.operation_queue.put({
            'type': 'save_message',
            'message_id': message_id,
            'user_id': user_id,
            'chat_id': chat_id,
            'role': role,
            'content': content,
            'llm_model': llm_model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cache_creation_input_tokens': cache_creation_input_tokens,
            'cache_read_input_tokens': cache_read_input_tokens
        })

        logger.debug(
            "message_queued",
            message_id=message_id,
            queue_size=self.operation_queue.qsize(),
            role=role
        )
        return message_id
    
    def update_chat_title(self, user_id: str, chat_id: str, title: str) -> bool:
        """
        Queue chat title update with validation (non-blocking).
        """
        # Validate inputs
        try:
            validate_user_id(user_id)
            validate_chat_id(chat_id)
            
            if not title or not isinstance(title, str):
                raise ValidationError(f"Invalid title: {title}", details={"title": title})
            
            if len(title) > 500:
                raise ValidationError(f"Title too long: {len(title)} chars", details={"length": len(title)})
            
        except ValidationError as e:
            logger.error(
                "update_title_validation_failed",
                error=str(e),
                user_id=user_id,
                chat_id=chat_id
            )
            raise
        
        self.operation_queue.put({
            'type': 'update_title',
            'user_id': user_id,
            'chat_id': chat_id,
            'title': title.strip()
        })
    
        logger.debug(
            "title_update_queued",
            chat_id=chat_id,
            title=title.strip()
        )
        return True
    
    def soft_delete_chat(self, user_id: str, chat_id: str) -> bool:
        """
        Queue chat deletion with validation (non-blocking).
        """
        # Validate inputs
        try:
            validate_user_id(user_id)
            validate_chat_id(chat_id)

        except ValidationError as e:
            logger.error(
                "delete_chat_validation_failed",
                error=str(e),
                user_id=user_id,
                chat_id=chat_id
            )
            raise

        try:
            invalidate_ownership_cache(chat_id)
        except Exception as e:
            logger.warning(
                "cache_invalidation_failed",
                error=str(e),
                chat_id=chat_id
            )

        self.operation_queue.put({
            'type': 'delete_chat',
            'user_id': user_id,
            'chat_id': chat_id
        })

        logger.debug(
            "chat_deletion_queued",
            chat_id=chat_id,
            user_id=user_id
        )
        return True
    
    # Synchronous read operations (these still block, but reads are fast)
    @performance_monitor.track_operation("load_user_chats")
    def load_user_chats(self, user_id: str) -> Dict[str, ChatDict]:
        """
        Load conversation metadata for a user (synchronous, but fast).
        """
        validate_user_id(user_id)
        
        op_logger = OperationLogger("load_user_chats")
        
        with op_logger.track(user_id=user_id):
            try:
                db_manager = get_db_manager()
                with db_manager.get_connection() as connection:
                    with connection.cursor() as cursor:
                        query = f"""
                        SELECT 
                            c.chat_id,
                            c.title,
                            c.created_at,
                            COALESCE(MAX(m.created_at), c.updated_at) as updated_at,
                            COUNT(m.message_id) as message_count
                        FROM {db_manager.catalog}.{db_manager.schema}.{CONVERSATIONS_TABLE} c
                        LEFT JOIN {db_manager.catalog}.{db_manager.schema}.{MESSAGES_TABLE} m
                            ON c.chat_id = m.chat_id 
                            AND c.user_id = m.user_id 
                            AND m.deleted = FALSE
                        WHERE c.user_id = ? AND c.deleted = FALSE
                        GROUP BY c.chat_id, c.title, c.created_at, c.updated_at
                        ORDER BY updated_at DESC
                        LIMIT {MAX_RECENT_CHATS}
                        """
                        
                        cursor.execute(query, (user_id,))
                        
                        chats: Dict[str, ChatDict] = {}
                        for row in cursor.fetchall():
                            chat_id = row[0]
                            chats[chat_id] = {
                                "title": row[1],
                                "created_at": row[2],
                                "updated_at": row[3],
                                "message_count": row[4],
                                "messages": None,  # Lazy load
                                "loaded_at": None
                            }
                        
                        logger.info(
                            "user_chats_loaded",
                            user_id=user_id,
                            chat_count=len(chats)
                        )
                        return chats
                        
            except Exception as e:
                logger.error(
                    "load_chats_failed",
                    error=str(e),
                    user_id=user_id
                )
                return {}
    
    @performance_monitor.track_operation("load_conversation_messages")
    def load_conversation_messages(self, user_id: str, chat_id: str) -> List[MessageDict]:
        """
        Load all messages for a conversation (synchronous, but fast).
        """
        validate_user_id(user_id)
        validate_chat_id(chat_id)
        
        op_logger = OperationLogger("load_conversation_messages")
        
        with op_logger.track(user_id=user_id, chat_id=chat_id):
            try:
                db_manager = get_db_manager()
                with db_manager.get_connection() as connection:
                    with connection.cursor() as cursor:
                        # Verify ownership (cached after first check)
                        try:
                            verify_ownership_with_cache(chat_id, user_id)
                        except PermissionError:
                            logger.warning("unauthorized_access_attempt", user_id=user_id, chat_id=chat_id)
                            return []

                        query = f"""
                        SELECT role, content, created_at, llm_model, input_tokens, output_tokens,
                               cache_creation_input_tokens, cache_read_input_tokens
                        FROM {db_manager.catalog}.{db_manager.schema}.{MESSAGES_TABLE}
                        WHERE user_id = ? AND chat_id = ? AND deleted = FALSE
                        ORDER BY created_at ASC, message_id ASC
                        """

                        cursor.execute(query, (user_id, chat_id))

                        messages: List[MessageDict] = []
                        for row in cursor.fetchall():
                            messages.append({
                                "role": row[0],
                                "content": row[1],
                                "created_at": row[2],
                                "llm_model": row[3],
                                "input_tokens": row[4] or 0,
                                "output_tokens": row[5] or 0,
                                "cache_creation_input_tokens": row[6] or 0,
                                "cache_read_input_tokens": row[7] or 0
                            })
                        
                        logger.info(
                            "conversation_messages_loaded",
                            user_id=user_id,
                            chat_id=chat_id,
                            message_count=len(messages)
                        )
                        return messages
                        
            except Exception as e:
                logger.error(
                    "load_messages_failed",
                    error=str(e),
                    user_id=user_id,
                    chat_id=chat_id
                )
                return []
    
    def get_stats(self) -> ServiceStats:
        """Get service statistics."""
        with self._stats_lock:
            success_rate = (
                (self._total_operations - self._failed_operations) / 
                max(self._total_operations, 1) * 100
                if self._total_operations > 0 else 100.0
            )
            
            return {
                "strategy": "async_single_worker",
                "queue_size": self.operation_queue.qsize(),
                "worker_alive": self.worker.is_alive(),
                "total_operations": self._total_operations,
                "failed_operations": self._failed_operations,
                "success_rate": round(success_rate, 2),
                "queuing": True,
                "batching": False,
                "workers": 1,
                "initialized": getattr(self, '_initialized', False)
            }

    def _initialize(self) -> None:
        """Internal initialization method (called within lock)."""
        # Single queue for all operations
        self.operation_queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        
        # Statistics tracking
        self._total_operations: int = 0
        self._failed_operations: int = 0
        self._stats_lock: threading.Lock = threading.Lock()
        
        # Shutdown flag
        self._shutdown: bool = False
        
        # Single background worker
        self.worker: threading.Thread = threading.Thread(
            target=self._worker, 
            daemon=True, 
            name="DB-Worker"
        )
        self.worker.start()
        
        # Register cleanup
        atexit.register(self._cleanup)
        
        logger.info("db_service_initialized", strategy="async_single_worker")
        
        # Mark as initialized
        self._initialized: bool = True


@st.cache_resource(show_spinner=False)
def get_db_service() -> DBService:
    """
    Get singleton instance of DBService.
    Uses Streamlit's cache_resource to share across all sessions.
    """
    return DBService()
"""
Async activity logging. A single background worker, no batching.
Includes performance monitoring and retry logic.
"""
import threading
import queue
import time
import atexit
import streamlit as st
from datetime import datetime, date
from typing import Optional, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.constants import ACTIVITY_LOG_TABLE
from config.config_loader import config
from config.types import MessageType, ServiceStats

from services.db_connection_manager import get_db_manager

from utils.monitoring.performance_monitor import performance_monitor
from utils.core.id_generator import generate_log_id
from utils.core.structured_logger import get_logger

logger = get_logger(__name__)

class DBLogger:
    """Async logger: writes happen in background thread."""
    _instance: Optional['DBLogger'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls) -> 'DBLogger':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        with self._lock:
            if self._initialized:
                logger.debug("DBLogger already initialized, skipping")
                return
            
            # Check if logging is explicitly disabled
            logging_enabled = config.get('logging_enabled', True)
            if not logging_enabled:
                logger.info("Logging disabled by configuration")
                self._disabled = True
                self._initialized = True
                return
            
            logger.info("DBLogger initializing (async, single worker)...")
            self._initialize()
    
    def _cleanup(self) -> None:
        """Graceful shutdown: wait for pending logs."""
        if self._shutdown:
            return
        
        pending = self.log_queue.qsize()
        if pending > 0:
            timeout = config.get('database.timeouts.cleanup_timeout_seconds', 10)
            check_interval = config.get('database.timeouts.worker_check_interval_seconds', 1.0)
            
            logger.info(f"DBLogger: Waiting for {pending} pending logs (timeout: {timeout}s)...")
            
            start = time.time()
            
            while not self.log_queue.empty() and (time.time() - start) < timeout:
                if not self.worker.is_alive():
                    logger.error("Worker thread died during cleanup")
                    break
                time.sleep(check_interval)
            
            remaining = self.log_queue.qsize()
            if remaining == 0:
                logger.info("DBLogger: All logs completed")
            else:
                logger.warning(f"DBLogger: {remaining} logs incomplete after {timeout}s timeout")
        
        self._shutdown = True
        logger.info("DBLogger shutdown complete")
    
    def _worker(self) -> None:
        """Background worker that processes logs one at a time."""
        logger.debug("DBLogger worker started")
        
        while not self._shutdown:
            try:
                # Wait for next log entry
                try:
                    log_data: Tuple = self.log_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Write to database
                try:
                    self._write_log_to_db(log_data)
                    
                    # Track successful log
                    with self._stats_lock:
                        self._total_logs += 1
                        
                except Exception as e:
                    logger.error(f"Error writing log: {e}")
                    with self._stats_lock:
                        self._total_logs += 1
                        self._failed_logs += 1
                finally:
                    self.log_queue.task_done()
                    
            except Exception as e:
                logger.error(f"Error in logger worker: {e}")
        
        logger.info("DBLogger worker exiting")
    
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
    @performance_monitor.track_operation("write_activity_log")
    def _write_log_to_db(self, log_data: Tuple) -> None:
        """
        Actually write log to database (called by worker).
        
        Args:
            log_data: Tuple containing log entry data
        
        Raises:
            Exception: If database operation fails
        """
        try:
            db_manager = get_db_manager()
            with db_manager.get_connection() as connection:
                with connection.cursor() as cursor:
                    query = f"""
                    INSERT INTO {db_manager.catalog}.{db_manager.schema}.{ACTIVITY_LOG_TABLE}
                    (log_id, log_date, timestamp, user_name, user_email, user_id, chat_id,
                    message_id, message_type, selected_llm, input_tokens, output_tokens,
                    cache_creation_input_tokens, cache_read_input_tokens,
                    session_id, ip_address, user_agent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    
                    cursor.execute(query, log_data)
                    connection.commit()
                    
                    logger.debug(f"✓ Logged activity for message {log_data[7]}")
                    
        except Exception as e:
            logger.error(f"Error writing log to database: {e}")
            raise
    
    def log_message(
        self, 
        user_id: str, 
        message_id: str, 
        message_type: MessageType, 
        chat_id: str,
        selected_llm: Optional[str] = None, 
        input_tokens: int = 0, 
        output_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
        user_name: Optional[str] = None, 
        user_email: Optional[str] = None, 
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None, 
        user_agent: Optional[str] = None
    ) -> bool:
        """
        Queue log entry (non-blocking, returns immediately).
        Actual DB write happens in background thread.
        
        Args:
            user_id: Unique identifier for the user
            message_id: Unique identifier for the message
            message_type: Type of message (user/assistant)
            chat_id: Unique identifier for the conversation
            selected_llm: Optional LLM model identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cache_creation_input_tokens: Number of cache creation input tokens
            cache_read_input_tokens: Number of cache read input tokens
            user_name: Optional user display name
            user_email: Optional user email
            session_id: Optional session identifier
            ip_address: Optional IP address
            user_agent: Optional user agent string
        
        Returns:
            True if successfully queued
        """
        log_id = generate_log_id()
        timestamp = datetime.now()
        log_date: date = timestamp.date()
        
        log_data: Tuple = (
            log_id, log_date, timestamp, user_name, user_email, user_id, chat_id,
            message_id, message_type, selected_llm, input_tokens or 0, output_tokens or 0,
            cache_creation_input_tokens or 0, cache_read_input_tokens or 0,
            session_id, ip_address, user_agent
        )
        
        self.log_queue.put(log_data)
        logger.debug(f"Queued log entry (queue: {self.log_queue.qsize()})")
        return True
    
    def get_stats(self) -> ServiceStats:
        """
        Get logger statistics.
        
        Returns:
            Dictionary containing logger statistics
        """
        with self._stats_lock:
            success_rate = (
                (self._total_logs - self._failed_logs) / 
                max(self._total_logs, 1) * 100
                if self._total_logs > 0 else 100.0
            )
            
            return {
                "strategy": "async_single_worker",
                "queue_size": self.log_queue.qsize(),
                "worker_alive": self.worker.is_alive(),
                "total_logs": self._total_logs,
                "failed_logs": self._failed_logs,
                "success_rate": round(success_rate, 2),
                "queuing": True,
                "batching": False,
                "workers": 1,
                "initialized": getattr(self, '_initialized', False)
            }

    def _initialize(self) -> None:
        """Internal initialization method (called within lock)."""
        # Single queue for log entries
        self.log_queue: queue.Queue[Tuple] = queue.Queue()
        
        # Statistics tracking
        self._total_logs: int = 0
        self._failed_logs: int = 0
        self._stats_lock: threading.Lock = threading.Lock()
        
        # Shutdown flag
        self._shutdown: bool = False
        
        # Single background worker
        self.worker: threading.Thread = threading.Thread(
            target=self._worker, 
            daemon=True, 
            name="DBLogger-Worker"
        )
        self.worker.start()
        
        # Register cleanup
        atexit.register(self._cleanup)
        
        logger.info("DBLogger initialized (async mode)")
        
        # Mark as initialized
        self._initialized: bool = True

@st.cache_resource(show_spinner=False)
def get_db_logger() -> DBLogger:
    """
    Get singleton instance of DBLogger.
    Uses Streamlit's cache_resource to share across all sessions.
    """
    return DBLogger()
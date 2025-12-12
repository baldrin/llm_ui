"""
Database connection manager with connection pooling and health monitoring.
Optimized for Databricks Apps multi-user environment.
"""
import threading
import time
import atexit
import streamlit as st
import re
from contextlib import contextmanager
from threading import Semaphore
from typing import Optional, Generator
from databricks import sql
from databricks.sql.client import Connection
from dotenv import load_dotenv
from queue import Queue, Empty

from config.config_loader import config
from config.types import DatabaseStats
from config.exceptions import DatabaseError

from utils.core.structured_logger import get_logger

logger = get_logger(__name__)

load_dotenv()

class ConnectionWrapper:
    """Wrapper to track connection usage for validation optimization."""

    def __init__(self, connection: Connection, is_pooled: bool = True):
        self.connection = connection
        self.created_at = time.time()
        self.last_used = time.time()
        self.last_validated = time.time()
        self.use_count = 0
        self.is_pooled = is_pooled

    def mark_used(self) -> None:
        """Mark connection as recently used."""
        self.last_used = time.time()
        self.use_count += 1

    def needs_validation(self, threshold: float) -> bool:
        """Check if connection needs validation based on idle time."""
        return (time.time() - self.last_validated) > threshold
    
    def get_age(self) -> float:
        """Get connection age in seconds."""
        return time.time() - self.created_at

    def is_stale(self, max_age: float = 3600) -> bool:
        """Check if connection is too old (default: 1 hour)."""
        return self.get_age() > max_age


class DatabaseConnectionManager:
    """
    Singleton connection manager with pooling and health monitoring.
    
    Features:
    - Shared connection pool across all users
    - Lazy validation (only when idle > threshold)
    - Background health monitoring (non-blocking)
    - Thread-safe operations
    - Graceful shutdown
    """
    _instance: Optional['DatabaseConnectionManager'] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> 'DatabaseConnectionManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        with self._lock:
            if self._initialized:
                logger.debug("DatabaseConnectionManager already initialized, skipping")
                return

            logger.info("Initializing DatabaseConnectionManager (shared pool with background health monitoring)")
            self._initialize()

    def is_offline_mode(self) -> bool:
        return getattr(self, '_offline_mode', False)

    def _create_connection(self, is_pooled: bool = True) -> ConnectionWrapper:
        if self._offline_mode:
            raise RuntimeError("Cannot create connection in offline mode")

        try:
            logger.debug(f"Creating new database connection (pooled={is_pooled})")

            connection = sql.connect(
                server_hostname=self.server_hostname,
                http_path=self.http_path,
                access_token=self.access_token,
                catalog=self.catalog,
                schema=self.schema
            )

            wrapper = ConnectionWrapper(connection, is_pooled=is_pooled)
            logger.debug(f"Successfully created connection (pooled={is_pooled})")
            return wrapper

        except Exception as e:
            logger.error(f"Failed to create database connection: {e}")
            raise DatabaseError(
                "Failed to create database connection",
                details={
                    "host": self.server_hostname,
                    "catalog": self.catalog,
                    "schema": self.schema,
                    "error": str(e)
                }
            )

    def _health_monitor_loop(self) -> None:
        """Background thread that monitors pool health."""
        logger.info("Health monitor thread started")
        
        # Get configuration
        startup_delay = config.get(
            'database.connection.health_monitor_startup_delay_seconds',
            5
        )
        check_interval = config.get(
            'database.connection.health_check_interval_seconds', 
            30
        )
        
        # Delay before running check after startup
        if startup_delay > 0:
            logger.debug(f"Health monitor waiting {startup_delay}s before first check")
            if self._shutdown_event.wait(timeout=startup_delay):
                logger.info("Health monitor received shutdown during startup delay")
                return
        
        if not self._shutdown_event.is_set():
            logger.debug("Running initial health check")
            try:
                self._ensure_pool_health()
            except Exception as e:
                logger.error(f"Initial health check error: {e}")
        
        # Main monitoring loop
        while not self._shutdown_event.is_set():
            # Wait for check_interval or shutdown signal
            if self._shutdown_event.wait(timeout=check_interval):
                # Shutdown was signaled
                break
            
            try:
                logger.debug("Running scheduled health check")
                self._ensure_pool_health()
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
        
        logger.info("Health monitor thread exiting")

    def _ensure_pool_health(self) -> None:
        """
        Monitor and maintain connection pool health.
        Only recreates connections if pooled connections are actually missing.
        """
        if self._offline_mode:
            return

        # Non-blocking acquire if health check is running, skip
        acquired = self._health_check_lock.acquire(blocking=False)
        if not acquired:
            logger.debug("Health check already in progress, skipping")
            return

        try:
            # Get current pool state
            with self._pooled_connections_lock:
                pooled_connections_created = self._pooled_connections_created
                with self._pool_lock:
                    current_available = self.connection_pool.qsize()
                    target_size = self.pool_size
                
            # Calculate thresholds
            threshold = config.get('database.connection.health_check_threshold', 0.5)
            min_healthy_pooled = int(target_size * threshold)
            
            # Check if we've lost pooled connections
            # not just if they're being used
            pooled_in_use = pooled_connections_created - current_available
            
            logger.debug(
                f"Health check: {current_available} available, "
                f"{pooled_in_use} in use, "
                f"{pooled_connections_created} total pooled "
                f"(target: {target_size}, min: {min_healthy_pooled})"
            )
            
            # Recreate only if we've actually lost pooled connections
            if pooled_connections_created >= min_healthy_pooled:
                logger.debug(
                    f"Pool health OK: {pooled_connections_created} pooled connections >= "
                    f"{min_healthy_pooled} minimum"
                )
                return
            
            # We've lost connections, time to recreate them
            connections_to_create = target_size - pooled_connections_created
            
            logger.warning(
                f"Connection pool depleted: only {pooled_connections_created}/{target_size} "
                f"pooled connections exist (min: {min_healthy_pooled}). "
                f"Recreating {connections_to_create} connections..."
            )

            created = 0
            failed_attempts = 0
            max_consecutive_failures = config.get(
                'database.connection.health_check_max_failures',
                3
            )

            for i in range(connections_to_create):
                try:
                    # Create new pooled connection
                    wrapper = self._create_connection(is_pooled=True)
                    failed_attempts = 0

                    # Add to pool
                    with self._pool_lock:
                        if self.connection_pool.qsize() < target_size:
                            self.connection_pool.put_nowait(wrapper)
                            with self._pooled_connections_lock:
                                self._pooled_connections_created += 1
                            created += 1
                            logger.debug(
                                f"Recreated connection {i+1}/{connections_to_create} "
                                f"(total pooled: {self._pooled_connections_created})"
                            )
                        else:
                            # Pool already full, could happen if another thread already added connections
                            try:
                                wrapper.connection.close()
                            except Exception:
                                pass
                            logger.debug(
                                "Pool already replenished, discarding connection"
                            )
                            break

                except Exception as e:
                    logger.error(f"Failed to recreate connection {i+1}: {e}")
                    failed_attempts += 1

                    if failed_attempts >= max_consecutive_failures:
                        logger.error(
                            f"Stopping health check after {failed_attempts} "
                            f"consecutive failures. Cluster may be unavailable."
                        )
                        break

            if created > 0:
                with self._pool_lock:
                    final_available = self.connection_pool.qsize()
                with self._pooled_connections_lock:
                    final_pooled = self._pooled_connections_created
                logger.info(
                    f"Successfully recreated {created} connections. "
                    f"Pool: {final_available} available, {final_pooled} total pooled"
                )
            else:
                logger.error(
                    "Failed to recreate any connections. Pool remains depleted. "
                    "Check Databricks cluster status."
                )

        except Exception as e:
            logger.error(f"Error in pool health check: {e}")
        finally:
            self._health_check_lock.release()

    def _extract_sqlstate(self, error: Exception) -> Optional[str]:
        """Extract SQLSTATE code from Databricks error message."""
        error_str = str(error)

        match = re.search(r'SQLSTATE:\s*([0-9A-Z]{5})', error_str, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def _is_connection_error(self, error: Exception) -> bool:
        """
        Determine if an error indicates a bad connection vs a query error.
        Uses SQLSTATE codes when available for accurate detection.
        """
        # Try to get SQLSTATE code
        sqlstate = self._extract_sqlstate(error)

        if sqlstate:
            # Class 08: Connection exceptions: ALWAYS a connection error
            if sqlstate.startswith('08'):
                logger.debug(
                    f"Connection error detected via SQLSTATE: {sqlstate}"
                )
                return True

            # Class 42: Syntax/semantic errors: NOT a connection error
            if sqlstate.startswith('42'):
                logger.debug(
                    f"Query error detected via SQLSTATE: {sqlstate} "
                    "(connection is healthy)"
                )
                return False

            # Class 22: Data exceptions: NOT a connection error
            if sqlstate.startswith('22'):
                logger.debug(
                    f"Data error detected via SQLSTATE: {sqlstate} "
                    "(connection is healthy)"
                )
                return False

            # Class 23: Integrity constraint violations: NOT a connection error
            if sqlstate.startswith('23'):
                logger.debug(
                    f"Constraint violation detected via SQLSTATE: {sqlstate} "
                    "(connection is healthy)"
                )
                return False

            # Class XX: Internal errors: could a be connection issue
            if sqlstate.startswith('XX'):
                logger.warning(
                    f"Internal error detected via SQLSTATE: {sqlstate} "
                    "(treating as connection error)"
                )
                return True

        # Fallback: Check Python exception types
        if isinstance(error, (ConnectionError, TimeoutError)):
            logger.debug("Connection error detected via exception type")
            return True

        # Fallback: Check error message for connection-related keywords
        error_str = str(error).lower()
        connection_keywords = [
            'connection closed',
            'connection lost',
            'connection refused',
            'connection timeout',
            'connection reset',
            'connection failure',
            'broken pipe',
            'network error',
            'socket error',
            'unable to establish',
            'cannot establish connection',
            'server unreachable',
            'cluster unreachable'
        ]

        if any(keyword in error_str for keyword in connection_keywords):
            logger.debug(
                f"Connection error detected via keyword match: "
                f"{[k for k in connection_keywords if k in error_str]}"
            )
            return True

        # Default: assume it's a query error, the connection is probalby fine
        logger.debug(
            "No connection error indicators found: treating as query error "
            "(connection is healthy)"
        )
        return False

    def _track_error(self, error: Exception, is_connection_error: bool) -> None:
        """Track error statistics for monitoring."""
        with self._stats_lock:
            if is_connection_error:
                self._connection_errors += 1
            else:
                self._query_errors += 1

    def get_fully_qualified_table_name(self, table_name: str) -> str:
        """Get a fully qualified table name with catalog and schema."""
        return f"{self.catalog}.{self.schema}.{table_name}"

    @contextmanager
    def get_connection(self) -> Generator[Connection, None, None]:
        """Get a connection from the pool (or create new if pool is empty)."""
        if self._offline_mode:
            logger.warning("Attempted to get connection in offline mode")
            raise RuntimeError("Database connection not available in offline mode")

        wrapper: Optional[ConnectionWrapper] = None
        from_pool = False

        with self.connection_semaphore:
            try:
                with self._stats_lock:
                    self._connection_requests += 1
                    request_num = self._connection_requests

                try:
                    wrapper = self.connection_pool.get_nowait()
                    from_pool = True
                    with self._stats_lock:
                        self._pool_hits += 1
                    logger.debug(f"Request #{request_num}: Got connection from pool")

                    max_age = config.get('database.connection.max_age', 3600)
                    if wrapper.is_stale(max_age):
                        logger.info(
                            f"Connection is {wrapper.get_age():.0f}s old (max: {max_age}s), "
                            "replacing with fresh connection"
                        )
                        
                        try:
                            wrapper.connection.close()
                        except Exception:
                            pass

                        with self._pooled_connections_lock:
                            self._pooled_connections_created -= 1

                        # Create fresh connection
                        wrapper = self._create_connection(is_pooled=True)
                        with self._pooled_connections_lock:
                            self._pooled_connections_created += 1

                    # Validate if connection has been idle too long
                    elif wrapper.needs_validation(self.validation_threshold):
                        try:
                            self._validate_connection(wrapper.connection)
                            wrapper.last_validated = time.time()
                            logger.debug(
                                f"Validated connection (idle for "
                                f"{time.time() - wrapper.last_used:.1f}s)"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Pooled connection invalid after "
                                f"{time.time() - wrapper.last_used:.1f}s idle, "
                                f"creating new one: {e}"
                            )
                            try:
                                wrapper.connection.close()
                            except Exception:
                                pass
                            
                            # Track that we lost a pooled connection
                            with self._pooled_connections_lock:
                                self._pooled_connections_created -= 1
                            
                            # Create new pooled connection
                            wrapper = self._create_connection(is_pooled=True)
                            with self._pooled_connections_lock:
                                self._pooled_connections_created += 1
                    else:
                        logger.debug(
                            f"Skipped validation (last validated "
                            f"{time.time() - wrapper.last_validated:.1f}s ago)"
                        )

                    wrapper.mark_used()

                except Empty:
                    # Pool is empty: create temporary connection up to the max temporary connections allowed
                    wrapper = self._create_connection(is_pooled=False)
                    with self._stats_lock:
                        self._pool_misses += 1
                    logger.debug(
                        f"Request #{request_num}: Created temporary connection (pool empty)"
                    )

                yield wrapper.connection

                logger.debug(f"Request #{request_num} completed successfully")

            except Exception as e:
                logger.error(f"Database operation failed in request #{request_num}: {e}")

                if wrapper and from_pool:
                    is_conn_error = self._is_connection_error(e)
                    self._track_error(e, is_conn_error)

                    if is_conn_error:
                        # Connection is bad: don't return it to the pool
                        try:
                            wrapper.connection.close()
                            sqlstate = self._extract_sqlstate(e)
                            logger.warning(
                                f"Closed failed connection (SQLSTATE: {sqlstate or 'unknown'})"
                            )
                        except Exception:
                            pass
                        finally:
                            # Track that we lost a pooled connection
                            with self._pooled_connections_lock:
                                self._pooled_connections_created -= 1
                            wrapper = None
                        
                        # Background thread will handle recreation
                    else:
                        sqlstate = self._extract_sqlstate(e)
                        logger.debug(
                            f"Query failed (SQLSTATE: {sqlstate or 'unknown'}) "
                            "but connection is healthy (will return to pool)"
                        )
                raise

            finally:
                if wrapper and from_pool:
                    try:
                        wrapper.mark_used()
                        self.connection_pool.put_nowait(wrapper)
                        logger.debug("Returned connection to pool")
                    except Exception as ex:
                        try:
                            wrapper.connection.close()
                            logger.warning(
                                f"Closed bad connection instead of returning to pool: {ex}"
                            )
                        except Exception:
                            pass
                        # Track that we lost a pooled connection
                        with self._pooled_connections_lock:
                            self._pooled_connections_created -= 1
                elif wrapper and not from_pool:
                    # Temporary connection: close it
                    try:
                        wrapper.connection.close()
                        logger.debug("Closed temporary connection")
                    except Exception:
                        pass

    def get_stats(self) -> DatabaseStats:
        """Get connection statistics including pool health."""
        base_stats: DatabaseStats = {
            "offline_mode": self._offline_mode,
            "database_enabled": getattr(self, 'database_enabled', False),
            "initialized": getattr(self, '_initialized', False),
            "connection_requests": 0,
            "pool_hits": 0,
            "pool_misses": 0,
            "hit_rate_percent": 0.0,
            "pool_size": 0,
            "pool_available": 0,
            "pool_in_use": 0,
            "pool_health_percent": 0.0,
            "max_connections": 0,
            "pooled_connections_created": 0,
            "connection_errors": 0,
            "query_errors": 0,
            "health_monitor_alive": False,
            "connection_strategy": "background_health_monitoring"
        }

        if self._offline_mode:
            return base_stats

        # Read all stats with proper locking
        with self._stats_lock:
            connection_requests = self._connection_requests
            pool_hits = self._pool_hits
            pool_misses = self._pool_misses
            connection_errors = self._connection_errors
            query_errors = self._query_errors

        with self._pool_lock:
            pool_available = self.connection_pool.qsize()

        with self._pooled_connections_lock:
            pooled_created = self._pooled_connections_created

        # Calculate derived stats
        hit_rate = (pool_hits / max(connection_requests, 1)) * 100
        pool_in_use = pooled_created - pool_available
        pool_health_percentage = (pooled_created / self.pool_size) * 100 if self.pool_size > 0 else 0

        return {
            "offline_mode": self._offline_mode,
            "database_enabled": getattr(self, 'database_enabled', False),
            "initialized": getattr(self, '_initialized', False),
            "connection_requests": connection_requests,
            "pool_hits": pool_hits,
            "pool_misses": pool_misses,
            "hit_rate_percent": round(hit_rate, 2),
            "pool_size": self.pool_size,
            "pool_available": pool_available,
            "pool_in_use": pool_in_use,
            "pool_health_percent": round(pool_health_percentage, 2),
            "max_connections": self.max_connections,
            "pooled_connections_created": pooled_created,
            "connection_errors": connection_errors,
            "query_errors": query_errors,
            "health_monitor_alive": self._health_monitor_thread.is_alive(),
            "connection_strategy": "background_health_monitoring"
        }

    def close_all_connections(self) -> None:
        """Close all connections in the pool (for cleanup)."""
        if self._offline_mode or not getattr(self, '_initialized', False):
            return

        logger.info("Closing all pooled connections...")
        closed = 0
        while not self.connection_pool.empty():
            try:
                wrapper = self.connection_pool.get_nowait()
                wrapper.connection.close()
                closed += 1
            except Exception:
                pass
        logger.info(f"Closed {closed} pooled connections")

    def _cleanup(self) -> None:
        """Graceful shutdown: stop health monitor and close connections."""
        if getattr(self, '_shutdown_event', None) and self._shutdown_event.is_set():
            return
        
        logger.info("DatabaseConnectionManager cleanup started")
        
        # Signal shutdown
        if hasattr(self, '_shutdown_event'):
            self._shutdown_event.set()
        
        # Wait for health monitor to exit
        if hasattr(self, '_health_monitor_thread') and self._health_monitor_thread.is_alive():
            cleanup_timeout = config.get('database.connection.cleanup_timeout_seconds', 5)
            logger.info(f"Waiting for health monitor thread to exit (timeout: {cleanup_timeout}s)...")
            self._health_monitor_thread.join(timeout=cleanup_timeout)
            if self._health_monitor_thread.is_alive():
                logger.warning("Health monitor thread did not exit cleanly")
            else:
                logger.info("Health monitor thread exited")
        
        # Close all connections
        self.close_all_connections()
        
        logger.info("DatabaseConnectionManager cleanup complete")

    def _initialize(self) -> None:
        """Internal initialization method (called within lock)."""
        self.database_enabled: bool = config.get('database_enabled', True)

        if not self.database_enabled:
            logger.info("Database disabled in configuration. Running in offline mode.")
            self._offline_mode = True
            self._initialized = True
            return

        self._offline_mode = False

        self.server_hostname: Optional[str] = config.get('databricks.server_hostname')
        self.http_path: Optional[str] = config.get('databricks.http_path')
        self.access_token: Optional[str] = config.get('databricks.token')
        self.catalog: Optional[str] = config.get('database.catalog')
        self.schema: Optional[str] = config.get('database.schema')

        logger.info(f"Database configuration: catalog={self.catalog}, schema={self.schema}")

        if not all([
            self.server_hostname, 
            self.http_path, 
            self.access_token, 
            self.catalog, 
            self.schema
        ]):
            logger.warning("Missing Databricks environment variables. Running in offline mode.")
            self._offline_mode = True
            self._initialized = True
            return

        self.pool_size: int = config.get('database.connection.pool_size', 5)
        self.max_connections: int = config.get('database.connection.max_concurrent', 10)

        self.validation_threshold: float = config.get(
            'database.connection.validation_threshold', 
            600  # 600 seconds = 10 minutes default
        )
        logger.info(
            f"Connection validation threshold: {self.validation_threshold}s "
            f"(connections idle longer will be validated before use)"
        )

        # Semaphore limits total concurrent connections
        self.connection_semaphore: Semaphore = Semaphore(self.max_connections)
        
        # Queue holds available pooled connections
        self.connection_pool: Queue[ConnectionWrapper] = Queue(maxsize=self.pool_size)
        
        # Locks
        self._pool_lock: threading.Lock = threading.Lock()
        self._health_check_lock: threading.Lock = threading.Lock()
        self._pooled_connections_lock: threading.Lock = threading.Lock()
        self._stats_lock: threading.Lock = threading.Lock()

        # Shutdown event (replaces boolean flag)
        self._shutdown_event: threading.Event = threading.Event()

        logger.info(
            f"Creating connection pool with {self.pool_size} connections "
            f"(max concurrent: {self.max_connections})..."
        )
        start_time = time.time()

        # Track pooled connections separately
        self._pooled_connections_created: int = 0

        for i in range(self.pool_size):
            try:
                wrapper = self._create_connection(is_pooled=True)
                self.connection_pool.put(wrapper)
                self._pooled_connections_created += 1
                logger.debug(f"Added connection {i+1}/{self.pool_size} to pool")
            except Exception as e:
                logger.error(f"Failed to create connection {i+1}: {e}")

        elapsed = time.time() - start_time
        logger.info(
            f"Connection pool initialized with {self.connection_pool.qsize()} connections "
            f"in {elapsed:.2f} seconds (avg {elapsed/max(self.pool_size, 1):.2f}s per connection) "
            f"(shared across all users)"
        )

        # Statistics tracking
        self._connection_requests: int = 0
        self._pool_hits: int = 0
        self._pool_misses: int = 0
        self._connection_errors: int = 0
        self._query_errors: int = 0

        # Start background health monitor
        health_check_mode = config.get('database.connection.health_check_mode', 'background')
        
        if health_check_mode == 'background':
            self._health_monitor_thread = threading.Thread(
                target=self._health_monitor_loop,
                daemon=True,
                name="DB-Health-Monitor"
            )
            self._initialized: bool = True
            self._health_monitor_thread.start()
            
            check_interval = config.get(
                'database.connection.health_check_interval_seconds', 
                30
            )
            startup_delay = config.get(
                'database.connection.health_monitor_startup_delay_seconds',
                5
            )
            logger.info(
                f"Background health monitor started "
                f"(startup delay: {startup_delay}s, check interval: {check_interval}s)"
            )
        else:
            logger.info("Health monitoring disabled (health_check_mode != 'background')")
            # Create a dummy thread object so stats don't break
            self._health_monitor_thread = threading.Thread()

        # Register cleanup
        atexit.register(self._cleanup)

    def _validate_connection(self, conn: Connection) -> bool:
        """Quick health check for database connection."""
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()  # Consume the result
            return True
        except Exception as e:
            logger.warning(f"Connection validation failed: {e}")
            raise


@st.cache_resource(show_spinner=False)
def get_db_manager() -> DatabaseConnectionManager:
    """
    Get singleton instance of DatabaseConnectionManager.
    Uses Streamlit's cache_resource to share across all sessions.
    """
    return DatabaseConnectionManager()  # __new__ ensures singleton
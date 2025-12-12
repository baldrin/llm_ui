"""
Structured logging utilities for better observability.
Uses structlog for structured logging with context.
"""
import logging
import structlog
from typing import Any, Dict, Optional
from datetime import datetime


def setup_structured_logging() -> None:
    """
    Configure structured logging for the application.
    Call this once at application startup.
    """
    import sys
    from config.config_loader import config
    
    log_level_name = config.get('logging.log_level', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    
    # Configure standard library logging to just pass through
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        force=True,
    )
    
    use_json_format = config.get('logging.use_json_format', False)
    use_colors = config.get('logging.use_colors', False)
    
    # If colors are set to "auto", detect terminal
    if use_colors == "auto":
        use_colors = sys.stdout.isatty()
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.add_logger_name,
            structlog.processors.CallsiteParameterAdder(
                [
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            ),
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure the formatter for stdlib logging
    handler = logging.StreamHandler()
    
    # Choose renderer based on config
    if use_json_format:
        processor = structlog.processors.JSONRenderer()
    else:
        processor = structlog.dev.ConsoleRenderer(colors=use_colors)
    
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=processor,
            foreign_pre_chain=[
                structlog.stdlib.add_logger_name,
                structlog.processors.CallsiteParameterAdder(
                    [structlog.processors.CallsiteParameter.LINENO]
                ),
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
            ],
        )
    )
    
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class LogContext:
    """
    Context manager for adding structured context to logs.
    """
    
    def __init__(self, **context: Any):
        self.context = context
    
    def __enter__(self) -> 'LogContext':
        structlog.contextvars.bind_contextvars(**self.context)
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        structlog.contextvars.unbind_contextvars(*self.context.keys())


class OperationLogger:
    """
    Helper for logging operations with timing and context.
    """
    
    def __init__(self, operation_name: str, logger: Optional[structlog.BoundLogger] = None):
        self.operation_name = operation_name
        self.logger = logger or structlog.get_logger()
    
    def track(self, **context: Any) -> 'OperationTracker':
        """Start tracking an operation with context."""
        return OperationTracker(self.operation_name, self.logger, context)


class OperationTracker:
    """Context manager for tracking operation execution."""
    
    def __init__(
        self, 
        operation_name: str, 
        logger: structlog.BoundLogger, 
        context: Dict[str, Any]
    ):
        self.operation_name = operation_name
        self.logger = logger
        self.context = context
        self.start_time: Optional[float] = None
    
    def __enter__(self) -> 'OperationTracker':
        self.start_time = datetime.now().timestamp()
        self.logger.debug(
            f"{self.operation_name}_started",
            **self.context
        )
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        duration_ms = (datetime.now().timestamp() - self.start_time) * 1000
        
        if exc_type is None:
            self.logger.info(
                f"{self.operation_name}_completed",
                duration_ms=round(duration_ms, 2),
                **self.context
            )
        else:
            self.logger.error(
                f"{self.operation_name}_failed",
                duration_ms=round(duration_ms, 2),
                error_type=exc_type.__name__,
                error_message=str(exc_val),
                **self.context
            )


def log_db_operation(
    operation: str,
    success: bool,
    duration_ms: float,
    **context: Any
) -> None:
    """Log a database operation with standard fields."""
    logger = structlog.get_logger()
    
    log_func = logger.info if success else logger.error
    log_func(
        "db_operation",
        operation=operation,
        success=success,
        duration_ms=round(duration_ms, 2),
        **context
    )


def log_llm_request(
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: float,
    success: bool = True,
    **context: Any
) -> None:
    """Log an LLM API request with token usage."""
    logger = structlog.get_logger()
    
    log_func = logger.info if success else logger.error
    log_func(
        "llm_request",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        duration_ms=round(duration_ms, 2),
        success=success,
        **context
    )


def log_user_action(
    action: str,
    user_id: str,
    **context: Any
) -> None:
    """Log a user action."""
    logger = structlog.get_logger()
    logger.info(
        "user_action",
        action=action,
        user_id=user_id,
        **context
    )
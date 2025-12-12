import time
from functools import wraps
from typing import Callable, Dict, Any, TypeVar, cast
from config.config_loader import config
from config.types import PerformanceStats

from utils.core.structured_logger import get_logger

logger = get_logger(__name__)

# Type variable for generic function decoration
F = TypeVar('F', bound=Callable[..., Any])


class PerformanceMonitor:
    """Monitor and track database operation performance."""
    
    def __init__(self) -> None:
        """Initialize the performance monitor."""
        self.enabled: bool = config.get('performance.enabled', True)
        self.slow_threshold: float = config.get('performance.slow_query_threshold_seconds', 1.0)
        self.log_all: bool = config.get('performance.log_all_queries', False)
        
        # Statistics
        self._total_operations: int = 0
        self._slow_operations: int = 0
        self._total_time: float = 0.0
        self._operation_times: Dict[str, Dict[str, Any]] = {}
    
    def track_operation(self, operation_name: str) -> Callable[[F], F]:
        """Decorator to track database operation performance."""
        def decorator(func: F) -> F:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if not self.enabled:
                    return func(*args, **kwargs)
                
                start_time = time.time()
                error_occurred = False
                
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    error_occurred = True
                    raise e
                finally:
                    elapsed = time.time() - start_time
                    self._record_operation(operation_name, elapsed, error_occurred)
            
            return cast(F, wrapper)
        return decorator
    
    def _record_operation(self, operation_name: str, elapsed: float, error_occurred: bool) -> None:
        """Record operation metrics."""
        self._total_operations += 1
        self._total_time += elapsed
        
        # Track by operation type
        if operation_name not in self._operation_times:
            self._operation_times[operation_name] = {
                'count': 0,
                'total_time': 0.0,
                'slow_count': 0,
                'error_count': 0
            }
        
        stats = self._operation_times[operation_name]
        stats['count'] += 1
        stats['total_time'] += elapsed
        
        if error_occurred:
            stats['error_count'] += 1
        
        # Log slow operations
        if elapsed > self.slow_threshold:
            self._slow_operations += 1
            stats['slow_count'] += 1
            logger.warning(
                f"Slow operation detected: {operation_name} took {elapsed:.2f}s "
                f"(threshold: {self.slow_threshold}s)"
            )
        elif self.log_all:
            logger.debug(f"Operation {operation_name} completed in {elapsed:.3f}s")
    
    def get_stats(self) -> PerformanceStats:
        """Get performance statistics."""
        if not self.enabled:
            return {
                "enabled": False,
                "total_operations": 0,
                "slow_operations": 0,
                "slow_percentage": 0.0,
                "average_time_seconds": 0.0,
                "total_time_seconds": 0.0,
                "slow_threshold_seconds": 0.0,
                "operations": {}
            }
        
        avg_time = self._total_time / max(self._total_operations, 1)
        slow_percentage = (self._slow_operations / max(self._total_operations, 1)) * 100
        
        operation_stats: Dict[str, Dict[str, Any]] = {}
        for op_name, stats in self._operation_times.items():
            operation_stats[op_name] = {
                'count': stats['count'],
                'avg_time': stats['total_time'] / max(stats['count'], 1),
                'slow_count': stats['slow_count'],
                'error_count': stats['error_count'],
                'error_rate': (stats['error_count'] / max(stats['count'], 1)) * 100
            }
        
        return {
            "enabled": True,
            "total_operations": self._total_operations,
            "slow_operations": self._slow_operations,
            "slow_percentage": round(slow_percentage, 2),
            "average_time_seconds": round(avg_time, 3),
            "total_time_seconds": round(self._total_time, 2),
            "slow_threshold_seconds": self.slow_threshold,
            "operations": operation_stats
        }
    
    def reset_stats(self) -> None:
        """
        Reset all statistics.
        """
        self._total_operations = 0
        self._slow_operations = 0
        self._total_time = 0.0
        self._operation_times = {}


# Global instance
performance_monitor: PerformanceMonitor = PerformanceMonitor()
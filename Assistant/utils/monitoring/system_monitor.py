"""System resource monitoring utilities."""

import psutil
import os
from typing import Dict, Any
import streamlit as st

from utils.core.structured_logger import get_logger

logger = get_logger(__name__)


class SystemMonitor:
    """Monitor system resources (CPU, memory, disk)."""

    @staticmethod
    def get_process_stats() -> Dict[str, Any]:
        """Get stats for current Python process."""
        try:
            process = psutil.Process(os.getpid())

            with process.oneshot():
                memory_info = process.memory_info()
                cpu_percent = process.cpu_percent(interval=0.1)

                return {
                    'pid': process.pid,
                    'cpu_percent': round(cpu_percent, 2),
                    'memory_mb': round(memory_info.rss / (1024 * 1024), 2),
                    'memory_percent': round(process.memory_percent(), 2),
                    'threads': process.num_threads(),
                    'status': process.status()
                }
        except Exception as e:
            logger.error("process_stats_failed", error=str(e))
            return {'error': str(e)}

    @staticmethod
    def get_system_stats() -> Dict[str, Any]:
        """Get overall system stats."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1, percpu=False)
            cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
            memory = psutil.virtual_memory()

            return {
                'cpu': {
                    'overall_percent': round(cpu_percent, 2),
                    'per_core': [round(x, 2) for x in cpu_per_core],
                    'core_count': psutil.cpu_count(logical=False),
                    'logical_count': psutil.cpu_count(logical=True)
                },
                'memory': {
                    'total_gb': round(memory.total / (1024**3), 2),
                    'available_gb': round(memory.available / (1024**3), 2),
                    'used_gb': round(memory.used / (1024**3), 2),
                    'percent': round(memory.percent, 2)
                }
            }
        except Exception as e:
            logger.error("system_stats_failed", error=str(e))
            return {'error': str(e)}

    @staticmethod
    def get_cache_stats() -> Dict[str, Any]:
        """Get cache statistics from session state."""
        try:
            # Image caches
            image_metadata_cache = st.session_state.get('image_metadata_cache', {})
            image_base64_cache = st.session_state.get('image_base64_cache', {})

            # Calculate base64 cache size
            total_base64_size = 0
            if image_base64_cache:
                for encoded, _ in image_base64_cache.values():
                    total_base64_size += len(encoded)

            # PDF caches
            pdf_metadata_cache = st.session_state.get('pdf_metadata_cache', {})

            return {
                'image_metadata': {
                    'entries': len(image_metadata_cache),
                    'size_kb': 'N/A'  # Metadata is small
                },
                'image_base64': {
                    'entries': len(image_base64_cache),
                    'size_mb': round(total_base64_size / (1024 * 1024), 2)
                },
                'pdf_metadata': {
                    'entries': len(pdf_metadata_cache),
                    'size_kb': 'N/A'
                }
            }
        except Exception as e:
            logger.error("cache_stats_failed", error=str(e))
            return {'error': str(e)}

    @staticmethod
    def get_top_processes(limit: int = 5) -> list:
        """Get top processes by memory usage."""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']):
                try:
                    info = proc.info
                    processes.append({
                        'pid': info['pid'],
                        'name': info['name'],
                        'memory_percent': round(info['memory_percent'], 2),
                        'cpu_percent': round(info['cpu_percent'], 2)
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Sort by memory usage
            processes.sort(key=lambda x: x['memory_percent'], reverse=True)
            return processes[:limit]
        except Exception as e:
            logger.error("top_processes_failed", error=str(e))
            return [{'error': str(e)}]


# Module-level instance for easy imports
system_monitor = SystemMonitor()
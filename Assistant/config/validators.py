"""
Configuration validators for the Developer Assistant application.

This module provides modular validators for different configuration sections,
making validation logic easier to test and maintain.
"""
from typing import Any, Dict, List
from utils.core.structured_logger import get_logger

logger = get_logger(__name__)


class ConfigValidator:
    """Base class for configuration validators."""
    
    def __init__(self, config_dict: Dict[str, Any]):
        """Initialize validator with configuration dictionary."""
        self.config = config_dict
        self.errors: List[str] = []
    
    def validate(self) -> List[str]:
        """Run validation and return list of errors."""
        raise NotImplementedError("Subclasses must implement validate()")
    
    def get_value(self, key_path: str, default: Any = None) -> Any:
        """Get config value using dot notation."""
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value


class AppConfigValidator(ConfigValidator):
    """Validator for app configuration section."""
    
    def validate(self) -> List[str]:
        """Validate app configuration."""
        self.errors = []
        
        # Check app title
        app_title = self.get_value('app.title')
        if not app_title or not isinstance(app_title, str):
            self.errors.append("app.title must be a non-empty string")
        
        # Check page title
        page_title = self.get_value('app.page_title')
        if not page_title or not isinstance(page_title, str):
            self.errors.append("app.page_title must be a non-empty string")
        
        # Validate context window
        context_window = self.get_value('llm.context_window_size')
        if context_window:
            if not isinstance(context_window, int):
                self.errors.append(
                    f"app.context_window_size must be an integer, got {type(context_window).__name__}"
                )
            elif context_window < 1000:
                self.errors.append(
                    f"app.context_window_size too small: {context_window} (minimum: 1000)"
                )
            elif context_window > 1_000_000:
                self.errors.append(
                    f"app.context_window_size too large: {context_window} (maximum: 1,000,000)"
                )
        
        # Validate max tokens
        max_tokens = self.get_value('llm.max_tokens')
        if max_tokens:
            if not isinstance(max_tokens, int):
                self.errors.append(
                    f"app.max_tokens must be an integer, got {type(max_tokens).__name__}"
                )
            elif max_tokens < 100:
                self.errors.append(
                    f"app.max_tokens too small: {max_tokens} (minimum: 100)"
                )
            elif max_tokens > 100_000:
                self.errors.append(
                    f"app.max_tokens too large: {max_tokens} (maximum: 100,000)"
                )
        
        # Validate temperature
        temperature = self.get_value('llm.temperature')
        if temperature is not None:
            if not isinstance(temperature, (int, float)):
                self.errors.append(
                    f"llm.temperature must be a number, got {type(temperature).__name__}"
                )
            elif temperature < 0.0 or temperature > 2.0:
                self.errors.append(
                    f"llm.temperature out of range: {temperature} (must be 0.0-2.0)"
                )
        
        return self.errors


class DatabaseConfigValidator(ConfigValidator):
    """Validator for database configuration section."""
    
    def validate(self) -> List[str]:
        """Validate database configuration."""
        self.errors = []
        
        pool_size = self.get_value('database.connection.pool_size')
        max_concurrent = self.get_value('database.connection.max_concurrent')
        
        if pool_size:
            if not isinstance(pool_size, int):
                self.errors.append(
                    f"database.connection.pool_size must be an integer, got {type(pool_size).__name__}"
                )
            elif pool_size < 1:
                self.errors.append(
                    f"database.connection.pool_size must be at least 1, got {pool_size}"
                )
        
        if max_concurrent:
            if not isinstance(max_concurrent, int):
                self.errors.append(
                    f"database.connection.max_concurrent must be an integer, got {type(max_concurrent).__name__}"
                )
            elif max_concurrent < 1:
                self.errors.append(
                    f"database.connection.max_concurrent must be at least 1, got {max_concurrent}"
                )
        
        # Validate pool_size <= max_concurrent
        if isinstance(pool_size, int) and isinstance(max_concurrent, int):
            if pool_size > max_concurrent:
                self.errors.append(
                    f"database.connection.pool_size ({pool_size}) cannot exceed "
                    f"max_concurrent ({max_concurrent})"
                )
        
        # Validate health check settings
        health_threshold = self.get_value('database.connection.health_check_threshold')
        if health_threshold is not None:
            if not isinstance(health_threshold, (int, float)):
                self.errors.append(
                    f"database.connection.health_check_threshold must be a number, "
                    f"got {type(health_threshold).__name__}"
                )
            elif health_threshold < 0.0 or health_threshold > 1.0:
                self.errors.append(
                    f"database.connection.health_check_threshold out of range: {health_threshold} "
                    f"(must be 0.0-1.0)"
                )
        
        health_interval = self.get_value('database.connection.health_check_interval')
        if health_interval is not None:
            if not isinstance(health_interval, int):
                self.errors.append(
                    f"database.connection.health_check_interval must be an integer, "
                    f"got {type(health_interval).__name__}"
                )
            elif health_interval < 1:
                self.errors.append(
                    f"database.connection.health_check_interval must be at least 1, "
                    f"got {health_interval}"
                )
        
        return self.errors


class LLMConfigValidator(ConfigValidator):
    """Validator for LLM models configuration."""
    
    def validate(self) -> List[str]:
        """Validate LLM models configuration."""
        self.errors = []
        
        llm_models = self.get_value('llm.llm_models')
        
        if llm_models:
            if not isinstance(llm_models, list):
                self.errors.append(
                    f"llm_models must be a list, got {type(llm_models).__name__}"
                )
            elif len(llm_models) == 0:
                self.errors.append(
                    "llm_models cannot be empty - at least one model must be configured"
                )
            else:
                for idx, model in enumerate(llm_models):
                    if not isinstance(model, dict):
                        self.errors.append(
                            f"llm_models[{idx}] must be a dictionary, got {type(model).__name__}"
                        )
                        continue
                    
                    model_name = model.get('name')
                    if not model_name:
                        self.errors.append(f"llm_models[{idx}] missing required field 'name'")
                    elif not isinstance(model_name, str) or not model_name.strip():
                        self.errors.append(f"llm_models[{idx}] has invalid 'name': {model_name}")
                    
                    model_id = model.get('id')
                    if not model_id:
                        self.errors.append(f"llm_models[{idx}] missing required field 'id'")
                    elif not isinstance(model_id, str) or not model_id.strip():
                        self.errors.append(f"llm_models[{idx}] has invalid 'id': {model_id}")
        
        return self.errors


class RetryConfigValidator(ConfigValidator):
    """Validator for retry configuration."""
    
    def validate(self) -> List[str]:
        """Validate retry configuration."""
        self.errors = []
        
        retry_attempts = self.get_value('database.retry.max_attempts')
        if retry_attempts:
            if not isinstance(retry_attempts, int):
                self.errors.append(
                    f"retry.max_attempts must be an integer, got {type(retry_attempts).__name__}"
                )
            elif retry_attempts < 1 or retry_attempts > 10:
                self.errors.append(
                    f"retry.max_attempts out of range: {retry_attempts} (must be 1-10)"
                )
        
        min_wait = self.get_value('database.retry.min_wait_seconds')
        if min_wait is not None:
            if not isinstance(min_wait, (int, float)):
                self.errors.append(
                    f"retry.min_wait_seconds must be a number, got {type(min_wait).__name__}"
                )
            elif min_wait < 0:
                self.errors.append(
                    f"retry.min_wait_seconds cannot be negative: {min_wait}"
                )
        
        max_wait = self.get_value('database.retry.max_wait_seconds')
        if max_wait is not None:
            if not isinstance(max_wait, (int, float)):
                self.errors.append(
                    f"retry.max_wait_seconds must be a number, got {type(max_wait).__name__}"
                )
            elif max_wait < 0:
                self.errors.append(
                    f"retry.max_wait_seconds cannot be negative: {max_wait}"
                )
        
        # Validate min_wait <= max_wait
        if isinstance(min_wait, (int, float)) and isinstance(max_wait, (int, float)):
            if min_wait > max_wait:
                self.errors.append(
                    f"retry.min_wait_seconds ({min_wait}) cannot exceed "
                    f"max_wait_seconds ({max_wait})"
                )
        
        return self.errors


class TimeoutConfigValidator(ConfigValidator):
    """Validator for timeout configuration."""
    
    def validate(self) -> List[str]:
        """Validate timeout configuration."""
        self.errors = []
        
        cleanup_timeout = self.get_value('database.timeouts.cleanup_timeout_seconds')
        if cleanup_timeout:
            if not isinstance(cleanup_timeout, (int, float)):
                self.errors.append(
                    f"timeouts.cleanup_timeout_seconds must be a number, "
                    f"got {type(cleanup_timeout).__name__}"
                )
            elif cleanup_timeout < 1 or cleanup_timeout > 300:
                self.errors.append(
                    f"timeouts.cleanup_timeout_seconds out of range: {cleanup_timeout} "
                    f"(must be 1-300)"
                )
        
        worker_check = self.get_value('database.timeouts.worker_check_interval_seconds')
        if worker_check is not None:
            if not isinstance(worker_check, (int, float)):
                self.errors.append(
                    f"timeouts.worker_check_interval_seconds must be a number, "
                    f"got {type(worker_check).__name__}"
                )
            elif worker_check < 0.1 or worker_check > 10:
                self.errors.append(
                    f"timeouts.worker_check_interval_seconds out of range: {worker_check} "
                    f"(must be 0.1-10)"
                )
        
        return self.errors


class PerformanceConfigValidator(ConfigValidator):
    """Validator for performance monitoring configuration."""
    
    def validate(self) -> List[str]:
        """Validate performance configuration."""
        self.errors = []
        
        slow_threshold = self.get_value('performance.slow_query_threshold_seconds')
        if slow_threshold:
            if not isinstance(slow_threshold, (int, float)):
                self.errors.append(
                    f"performance.slow_query_threshold_seconds must be a number, "
                    f"got {type(slow_threshold).__name__}"
                )
            elif slow_threshold < 0.1 or slow_threshold > 60:
                self.errors.append(
                    f"performance.slow_query_threshold_seconds out of range: {slow_threshold} "
                    f"(must be 0.1-60)"
                )
        
        return self.errors


class LoggingConfigValidator(ConfigValidator):
    """Validator for logging configuration."""
    
    def validate(self) -> List[str]:
        """Validate logging configuration."""
        self.errors = []
        
        log_level = self.get_value('log_level')
        if log_level:
            valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
            if log_level not in valid_levels:
                self.errors.append(
                    f"Invalid log_level: {log_level} (must be one of {valid_levels})"
                )
        
        return self.errors
    

class TitleGenerationConfigValidator(ConfigValidator):
    """Validator for title generation configuration."""
    
    def validate(self) -> List[str]:
        """Validate title generation configuration."""
        self.errors = []
        
        enabled = self.get_value('title_generation.enabled')
        if enabled is not None and not isinstance(enabled, bool):
            self.errors.append(
                f"title_generation.enabled must be a boolean, got {type(enabled).__name__}"
            )
        
        # Only validate other fields if enabled
        if enabled:
            model = self.get_value('title_generation.model')
            if not model or not isinstance(model, str):
                self.errors.append(
                    "title_generation.model must be a non-empty string when enabled"
                )
            
            max_tokens = self.get_value('title_generation.max_tokens')
            if max_tokens is not None:
                if not isinstance(max_tokens, int):
                    self.errors.append(
                        f"title_generation.max_tokens must be an integer, "
                        f"got {type(max_tokens).__name__}"
                    )
                elif max_tokens < 5 or max_tokens > 100:
                    self.errors.append(
                        f"title_generation.max_tokens out of range: {max_tokens} "
                        f"(must be 5-100)"
                    )
            
            temperature = self.get_value('title_generation.temperature')
            if temperature is not None:
                if not isinstance(temperature, (int, float)):
                    self.errors.append(
                        f"title_generation.temperature must be a number, "
                        f"got {type(temperature).__name__}"
                    )
                elif temperature < 0.0 or temperature > 2.0:
                    self.errors.append(
                        f"title_generation.temperature out of range: {temperature} "
                        f"(must be 0.0-2.0)"
                    )
        
        return self.errors
    
class TokenPricingConfigValidator(ConfigValidator):
    """Validator for token pricing configuration."""
    
    def validate(self) -> List[str]:
        """Validate token pricing configuration."""
        self.errors = []
        
        # Validate default input cost
        input_cost = self.get_value('token_pricing.default.input_cost_per_1k')
        if input_cost is None:
            self.errors.append("Missing 'token_pricing.default.input_cost_per_1k'")
        elif not isinstance(input_cost, (int, float)):
            self.errors.append(
                f"token_pricing.default.input_cost_per_1k must be a number, "
                f"got {type(input_cost).__name__}"
            )
        elif input_cost < 0:
            self.errors.append(
                f"token_pricing.default.input_cost_per_1k must be non-negative, "
                f"got {input_cost}"
            )
        
        # Validate default output cost
        output_cost = self.get_value('token_pricing.default.output_cost_per_1k')
        if output_cost is None:
            self.errors.append("Missing 'token_pricing.default.output_cost_per_1k'")
        elif not isinstance(output_cost, (int, float)):
            self.errors.append(
                f"token_pricing.default.output_cost_per_1k must be a number, "
                f"got {type(output_cost).__name__}"
            )
        elif output_cost < 0:
            self.errors.append(
                f"token_pricing.default.output_cost_per_1k must be non-negative, "
                f"got {output_cost}"
            )
        
        # Validate model-specific pricing (if present)
        models_pricing = self.get_value('token_pricing.models', {})
        if models_pricing and isinstance(models_pricing, dict):
            for model_name, pricing in models_pricing.items():
                if not isinstance(pricing, dict):
                    self.errors.append(
                        f"Invalid pricing structure for model '{model_name}' - must be a dictionary"
                    )
                    continue
                
                # Validate model input cost
                model_input = pricing.get('input_cost_per_1k')
                if model_input is None:
                    self.errors.append(
                        f"Missing 'input_cost_per_1k' for model '{model_name}'"
                    )
                elif not isinstance(model_input, (int, float)):
                    self.errors.append(
                        f"'input_cost_per_1k' for model '{model_name}' must be a number, "
                        f"got {type(model_input).__name__}"
                    )
                elif model_input < 0:
                    self.errors.append(
                        f"'input_cost_per_1k' for model '{model_name}' must be non-negative, "
                        f"got {model_input}"
                    )
                
                # Validate model output cost
                model_output = pricing.get('output_cost_per_1k')
                if model_output is None:
                    self.errors.append(
                        f"Missing 'output_cost_per_1k' for model '{model_name}'"
                    )
                elif not isinstance(model_output, (int, float)):
                    self.errors.append(
                        f"'output_cost_per_1k' for model '{model_name}' must be a number, "
                        f"got {type(model_output).__name__}"
                    )
                elif model_output < 0:
                    self.errors.append(
                        f"'output_cost_per_1k' for model '{model_name}' must be non-negative, "
                        f"got {model_output}"
                    )
        
        return self.errors


class UIConfigValidator(ConfigValidator):
    """Validator for UI configuration."""
    
    def validate(self) -> List[str]:
        """Validate UI configuration."""
        self.errors = []
        
        # Validate theme
        theme = self.get_value('ui.theme')
        if not theme:
            self.errors.append("Missing 'ui.theme'")
        elif not isinstance(theme, str):
            self.errors.append(
                f"ui.theme must be a string, got {type(theme).__name__}"
            )
        elif theme not in ['light', 'dark']:
            self.errors.append(
                f"Invalid ui.theme: '{theme}' (must be 'light' or 'dark')"
            )
        
        # Validate sidebar_width
        sidebar_width = self.get_value('ui.sidebar_width')
        if sidebar_width is not None:
            if not isinstance(sidebar_width, int):
                self.errors.append(
                    f"ui.sidebar_width must be an integer, got {type(sidebar_width).__name__}"
                )
            elif sidebar_width < 200 or sidebar_width > 600:
                self.errors.append(
                    f"ui.sidebar_width out of range: {sidebar_width} (must be 200-600)"
                )
        
        # Validate hide_streamlit_menu
        hide_menu = self.get_value('ui.hide_streamlit_menu')
        if hide_menu is not None and not isinstance(hide_menu, bool):
            self.errors.append(
                f"ui.hide_streamlit_menu must be a boolean, got {type(hide_menu).__name__}"
            )
        
        # Validate show_error_details
        show_errors = self.get_value('ui.show_error_details')
        if show_errors is not None and not isinstance(show_errors, bool):
            self.errors.append(
                f"ui.show_error_details must be a boolean, got {type(show_errors).__name__}"
            )
        
        # Validate toolbar_mode
        toolbar_mode = self.get_value('ui.toolbar_mode')
        if toolbar_mode is not None:
            if not isinstance(toolbar_mode, str):
                self.errors.append(
                    f"ui.toolbar_mode must be a string, got {type(toolbar_mode).__name__}"
                )
            elif toolbar_mode not in ['minimal', 'auto', 'developer']:
                self.errors.append(
                    f"Invalid ui.toolbar_mode: '{toolbar_mode}' "
                    f"(must be 'minimal', 'auto', or 'developer')"
                )
        
        return self.errors


class FeatureConfigValidator(ConfigValidator):
    """Validator for feature flags configuration."""
    
    def validate(self) -> List[str]:
        """Validate feature flags configuration."""
        self.errors = []
        
        # Validate model_selection feature
        model_selection = self.get_value('features.model_selection')
        if model_selection is None:
            self.errors.append("Missing feature flag 'features.model_selection'")
        elif not isinstance(model_selection, bool):
            self.errors.append(
                f"features.model_selection must be a boolean, "
                f"got {type(model_selection).__name__}"
            )
        
        # Validate chat_history feature
        chat_history = self.get_value('features.chat_history')
        if chat_history is None:
            self.errors.append("Missing feature flag 'features.chat_history'")
        elif not isinstance(chat_history, bool):
            self.errors.append(
                f"features.chat_history must be a boolean, "
                f"got {type(chat_history).__name__}"
            )
        
        # Validate file_attachments feature
        file_attachments = self.get_value('features.file_attachments')
        if file_attachments is None:
            self.errors.append("Missing feature flag 'features.file_attachments'")
        elif not isinstance(file_attachments, bool):
            self.errors.append(
                f"features.file_attachments must be a boolean, "
                f"got {type(file_attachments).__name__}"
            )
        
        return self.errors
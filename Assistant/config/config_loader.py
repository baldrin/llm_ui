"""
Centralized configuration manager with environment-specific config files.
"""
import os
import toml
from pathlib import Path
from typing import Any, Dict, Optional, List
from dotenv import load_dotenv

from config.exceptions import ConfigurationError
from utils.core.structured_logger import get_logger

logger = get_logger(__name__)

class Config:
    """
    Centralized configuration manager.
    Loads shared config (config.toml) and merges environment-specific overrides.
    Works for both local development (.env) and Databricks deployment (app.yaml).
    """
    _instance: Optional['Config'] = None
    
    def __init__(self) -> None:
        """Initialize configuration from shared and environment-specific TOML files."""
        self.project_root: Path = Path(__file__).parent.parent
    
        # Load .env for local development
        env_file = self.project_root / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            logger.info("Loaded .env file for local development")
        else:
            logger.debug("No .env file found (expected in Databricks Apps)")
        
        self.environment: str = os.getenv('APP_ENVIRONMENT', 'development').lower()
        logger.info(f"Running in '{self.environment}' environment")
        
        # Load shared configuration first
        self._config: Dict[str, Any] = self._load_shared_config()
        
        # Load and merge environment-specific config
        env_config = self._load_environment_config()
        self._deep_merge(self._config, env_config)
        
        # Apply environment variable overrides (for secrets)
        self._apply_env_overrides()
        
        # Validate configuration
        self._validate_config()
        
        logger.info(f"Configuration loaded for environment: {self.environment}")
    
    def _load_shared_config(self) -> Dict[str, Any]:
        """Load shared configuration that applies to all environments."""
        config_path = self.project_root / "config" / "config.toml"
        
        if not config_path.exists():
            raise ConfigurationError(
                "Shared configuration file not found",
                details={"path": str(config_path)}
            )
        
        try:
            config = toml.load(config_path)
            logger.info(f"Loaded shared configuration from: {config_path}")
            return config
        except Exception as e:
            raise ConfigurationError(
                "Failed to parse shared configuration file",
                details={"path": str(config_path), "error": str(e)}
            )
    
    def _load_environment_config(self) -> Dict[str, Any]:
        """Load environment-specific configuration."""
        config_path = self.project_root / "config" / f"config.{self.environment}.toml"
        
        if not config_path.exists():
            raise ConfigurationError(
                f"Configuration file not found for environment: {self.environment}",
                details={
                    "path": str(config_path),
                    "environment": self.environment,
                    "available_configs": self._list_available_configs()
                }
            )
        
        try:
            config = toml.load(config_path)
            logger.info(f"Loaded environment configuration from: {config_path}")
            return config
        except Exception as e:
            raise ConfigurationError(
                f"Failed to parse configuration file for {self.environment}",
                details={"path": str(config_path), "error": str(e)}
            )
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """
        Deep merge override dict into base dict.
        Override values take precedence.
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def _list_available_configs(self) -> List[str]:
        """List available configuration files for debugging."""
        config_dir = self.project_root / "config"
        if not config_dir.exists():
            return []
        
        configs = []
        for file in config_dir.glob("config.*.toml"):
            env_name = file.stem.replace("config.", "")
            configs.append(env_name)
        return configs
    
    def _apply_env_overrides(self) -> None:
        """
        Apply environment variable overrides for sensitive data.
        Useful for production where you don't want secrets in TOML files.
        These can come from .env (local) or app.yaml (Databricks).
        """
        overrides = {
            'DATABRICKS_TOKEN': ('databricks', 'token'),
            'DEBUG_MODE': ('debug', 'debug_enabled'),
            'LOG_LEVEL': ('logging', 'log_level')
        }
        
        for env_var, (section, key) in overrides.items():
            value = os.getenv(env_var)
            if value:
                if section not in self._config:
                    self._config[section] = {}
                
                # Handle boolean conversion for DEBUG_MODE
                if env_var == 'DEBUG_MODE':
                    value = value.lower() in ('true', '1', 'yes')
                
                self._config[section][key] = value
                logger.debug(f"Override: {section}.{key} from environment variable {env_var}")
    
    def _validate_config(self) -> None:
        """Validate critical configuration values using ALL modular validators."""
        from config.validators import (
            AppConfigValidator,
            DatabaseConfigValidator,
            LLMConfigValidator,
            RetryConfigValidator,
            TimeoutConfigValidator,
            PerformanceConfigValidator,
            LoggingConfigValidator,
            TitleGenerationConfigValidator,
            TokenPricingConfigValidator,
            UIConfigValidator,
            FeatureConfigValidator
        )
        
        all_errors: List[str] = []
        
        # Check required sections exist
        required_sections = ['app', 'database', 'databricks', 'environment']
        for section in required_sections:
            if not self.get(section):
                all_errors.append(f"Missing required config section: '{section}'")
        
        # Run ALL validators
        validators = [
            AppConfigValidator(self._config),
            DatabaseConfigValidator(self._config),
            LLMConfigValidator(self._config),
            RetryConfigValidator(self._config),
            TimeoutConfigValidator(self._config),
            PerformanceConfigValidator(self._config),
            LoggingConfigValidator(self._config),
            TitleGenerationConfigValidator(self._config),
            TokenPricingConfigValidator(self._config),
            UIConfigValidator(self._config),
            FeatureConfigValidator(self._config)
        ]
        
        for validator in validators:
            try:
                errors = validator.validate()
                all_errors.extend(errors)
            except Exception as e:
                logger.error(f"Validator {validator.__class__.__name__} failed: {e}")
                all_errors.append(f"Validator {validator.__class__.__name__} failed: {str(e)}")
        
        if all_errors:
            error_list = "\n  - ".join(all_errors)
            raise ConfigurationError(
                f"Configuration validation failed with {len(all_errors)} error(s):\n  - {error_list}",
                details={
                    "error_count": len(all_errors),
                    "errors": all_errors,
                    "environment": self.environment
                }
            )
        
        logger.info("Configuration validation passed")
    
    @classmethod
    def get_instance(cls) -> 'Config':
        """Get singleton instance of Config."""
        if cls._instance is None:
            cls._instance = Config()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (useful for testing)."""
        cls._instance = None
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation."""
        keys = key_path.split('.')
        value: Any = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_environment(self) -> str:
        """Get current environment name."""
        return self.environment
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == 'development'
    
    def is_test(self) -> bool:
        """Check if running in test environment."""
        return self.environment == 'test'
    
    def is_uat(self) -> bool:
        """Check if running in UAT environment."""
        return self.environment == 'uat'
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == 'production'
    
    def get_all(self) -> Dict[str, Any]:
        """Get entire configuration dictionary (for debugging)."""
        return self._config.copy()
    
    def get_environment_info(self) -> Dict[str, Any]:
        """Get current environment information for debugging."""
        return {
            'environment': self.environment,
            'databricks_host': self.get('databricks.host', 'Not set'),
            'database_catalog': self.get('database.catalog', 'Not set'),
            'database_schema': self.get('database.schema', 'Not set'),
            'user_name': self.get('user.name', 'Not set'),
            'debug_enabled': self.get('debug.debug_enabled', False),
            'show_sidebar_debug': self.get('debug.show_sidebar_debug', False),            
            'log_level': self.get('logging.log_level', 'INFO'),
            'available_configs': self._list_available_configs()
        }
    
    def validate_environment_variables(self) -> List[str]:
        """
        Validate required configuration values are present.
        
        Returns:
            List of missing or invalid configuration values
        """
        issues: List[str] = []
        
        # Required Databricks settings
        required_databricks = {
            'databricks.token': 'Databricks API token',
            'databricks.host': 'Databricks host',
            'databricks.server_hostname': 'Databricks server hostname',
            'databricks.http_path': 'Databricks SQL warehouse HTTP path',
        }
        
        for key_path, description in required_databricks.items():
            value = self.get(key_path)
            if not value:
                issues.append(f"{key_path} ({description}) is not set")
            elif isinstance(value, str) and not value.strip():
                issues.append(f"{key_path} ({description}) is empty")
        
        # Required database settings
        required_database = {
            'database.catalog': 'Database catalog name',
            'database.schema': 'Database schema name',
        }
        
        for key_path, description in required_database.items():
            value = self.get(key_path)
            if not value:
                issues.append(f"{key_path} ({description}) is not set")
        
        # Validate certificate path exists
        certs_path = self.get('databricks.certs_path')
        if certs_path:
            full_path = self.project_root / certs_path
            if not full_path.exists():
                issues.append(f"Databricks certs file not found: {full_path}")
        
        return issues


# Singleton config instance
config: Config = Config.get_instance()

# Convenience functions
def is_development() -> bool:
    """Check if running in development mode."""
    return config.is_development()

def is_production() -> bool:
    """Check if running in production mode."""
    return config.is_production()

def get_environment_info() -> Dict[str, Any]:
    """Get current environment information."""
    return config.get_environment_info()
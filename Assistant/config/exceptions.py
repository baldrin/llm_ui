"""
Custom exception classes for the Developer Assistant application.

This module defines a hierarchy of exceptions that provide clear,
actionable error messages for different failure scenarios.
"""
from typing import Optional, Any, Dict


class DeveloperAssistantError(Exception):
    """
    Base exception for all application errors.
    
    All custom exceptions inherit from this to allow catching
    any application-specific error with a single except clause.
    
    Attributes:
        message: Human-readable error message
        details: Optional dictionary with additional error context
    """
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the exception.
        
        Args:
            message: Error message describing what went wrong
            details: Optional dictionary with additional context
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class ConfigurationError(DeveloperAssistantError):
    """
    Configuration error - invalid or missing configuration.
    
    Raised when:
    - Required configuration values are missing
    - Configuration values are invalid
    - Configuration file cannot be loaded
    """
    pass


class ValidationError(DeveloperAssistantError):
    """
    Input validation error - invalid user input or data.
    
    Raised when:
    - User input fails validation
    - Data format is incorrect
    - Required fields are missing
    """
    pass


class DatabaseError(DeveloperAssistantError):
    """
    Database operation error.
    
    Raised when:
    - Database connection fails
    - Query execution fails
    - Transaction fails
    - Connection pool is exhausted
    """
    pass


class LLMError(DeveloperAssistantError):
    """
    LLM service error.
    
    Raised when:
    - LLM API call fails
    - Invalid model specified
    - Rate limit exceeded
    - Response parsing fails
    """
    pass


class AuthenticationError(DeveloperAssistantError):
    """
    Authentication/authorization error.
    
    Raised when:
    - User authentication fails
    - User validation fails
    - Missing required user information
    - Invalid credentials
    """
    pass


class ResourceNotFoundError(DeveloperAssistantError):
    """
    Resource not found error.
    
    Raised when:
    - Chat conversation not found
    - Message not found
    - User not found
    - File not found
    """
    pass


class ServiceUnavailableError(DeveloperAssistantError):
    """
    Service temporarily unavailable.
    
    Raised when:
    - Database is offline
    - LLM service is down
    - External dependency unavailable
    - System is in maintenance mode
    """
    pass


class RateLimitError(DeveloperAssistantError):
    """
    Rate limit exceeded.
    
    Raised when:
    - Too many requests to LLM API
    - Too many database queries
    - User exceeded usage quota
    """
    pass


class ContextWindowError(DeveloperAssistantError):
    """
    Context window limit exceeded.
    
    Raised when:
    - Conversation exceeds token limit
    - Message too large
    - Combined context too large
    """
    pass

class RequestSizeError(DeveloperAssistantError):
    """Raised when the request to the LLM exceeds the maximum allowed size."""
    pass
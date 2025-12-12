"""
Test custom exceptions and configuration validation.

Run from project root:
    python -m pytest tests/test_exceptions.py -v
    
Or:
    PYTHONPATH=. python tests/test_exceptions.py
"""
import sys
import pytest
from pathlib import Path

from config.exceptions import (
    DeveloperAssistantError,
    ConfigurationError,
    ValidationError,
    DatabaseError,
    LLMError,
    AuthenticationError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    RateLimitError,
    ContextWindowError
)

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))




def test_base_exception():
    """Test base exception class."""
    error = DeveloperAssistantError("Test error")
    assert str(error) == "Test error"
    assert error.message == "Test error"
    assert error.details == {}


def test_exception_with_details():
    """Test exception with details."""
    error = ValidationError(
        "Invalid input",
        details={"field": "user_id", "value": "abc"}
    )
    assert "Invalid input" in str(error)
    assert "field=user_id" in str(error)
    assert "value=abc" in str(error)


def test_configuration_error():
    """Test configuration error."""
    error = ConfigurationError(
        "Missing config",
        details={"missing_keys": ["app.title"]}
    )
    assert isinstance(error, DeveloperAssistantError)
    assert "Missing config" in str(error)


def test_validation_error():
    """Test validation error."""
    error = ValidationError(
        "Invalid user_id",
        details={"user_id": "abc", "min_length": 5}
    )
    assert isinstance(error, DeveloperAssistantError)
    assert "Invalid user_id" in str(error)


def test_database_error():
    """Test database error."""
    error = DatabaseError(
        "Connection failed",
        details={"host": "localhost", "port": 5432}
    )
    assert isinstance(error, DeveloperAssistantError)
    assert "Connection failed" in str(error)


def test_llm_error():
    """Test LLM error."""
    error = LLMError(
        "API request failed",
        details={"model": "claude-4", "status_code": 429}
    )
    assert isinstance(error, DeveloperAssistantError)
    assert "API request failed" in str(error)


def test_context_window_error():
    """Test context window error."""
    error = ContextWindowError(
        "Context limit exceeded",
        details={"current_tokens": 65000, "limit": 64000}
    )
    assert isinstance(error, DeveloperAssistantError)
    assert "Context limit exceeded" in str(error)


def test_exception_hierarchy():
    """Test exception hierarchy."""
    # All custom exceptions should inherit from DeveloperAssistantError
    exceptions = [
        ConfigurationError,
        ValidationError,
        DatabaseError,
        LLMError,
        AuthenticationError,
        ResourceNotFoundError,
        ServiceUnavailableError,
        RateLimitError,
        ContextWindowError
    ]
    
    for exc_class in exceptions:
        error = exc_class("Test")
        assert isinstance(error, DeveloperAssistantError)
        assert isinstance(error, Exception)


def test_exception_details_dict():
    """Test that details are properly stored."""
    details = {
        "user_id": "test123",
        "error_code": 404,
        "timestamp": "2024-01-01T12:00:00"
    }
    error = ResourceNotFoundError("User not found", details=details)
    
    assert error.details == details
    assert error.details["user_id"] == "test123"
    assert error.details["error_code"] == 404


def test_exception_without_details():
    """Test exception works without details."""
    error = DatabaseError("Connection timeout")
    assert error.details == {}
    assert str(error) == "Connection timeout"


if __name__ == "__main__":
    # Run tests
    print("Running exception tests...")
    pytest.main([__file__, "-v"])
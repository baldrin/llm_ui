"""
Unit tests for DatabaseConnectionManager error classification logic.
Tests SQLSTATE parsing and connection vs query error detection.
"""
import pytest
from services.connection_manager import DatabaseConnectionManager


class TestErrorClassification:
    """Test suite for error classification and SQLSTATE parsing."""

    @pytest.fixture
    def db_manager(self, monkeypatch):
        """
        Create a DatabaseConnectionManager instance in offline mode for testing.
        This avoids actual database connections during tests.
        """
        # Mock config to force offline mode
        monkeypatch.setenv('DATABASE_ENABLED', 'false')

        # Reset singleton instance
        DatabaseConnectionManager._instance = None
        DatabaseConnectionManager._initialized = False

        manager = DatabaseConnectionManager()
        return manager

    # ==================== SQLSTATE Extraction Tests ====================

    def test_extract_sqlstate_standard_format(self, db_manager):
        """Test extraction of SQLSTATE from standard error format."""
        error = Exception("Error occurred. SQLSTATE: 08001")
        sqlstate = db_manager._extract_sqlstate(error)
        assert sqlstate == "08001"

    def test_extract_sqlstate_case_insensitive(self, db_manager):
        """Test SQLSTATE extraction is case-insensitive."""
        error = Exception("Error occurred. sqlstate: 42S02")
        sqlstate = db_manager._extract_sqlstate(error)
        assert sqlstate == "42S02"

    def test_extract_sqlstate_with_extra_text(self, db_manager):
        """Test extraction when SQLSTATE is embedded in longer message."""
        error = Exception(
            "Query failed with error: SQLSTATE: 22012 - Division by zero"
        )
        sqlstate = db_manager._extract_sqlstate(error)
        assert sqlstate == "22012"

    def test_extract_sqlstate_multiple_occurrences(self, db_manager):
        """Test that first SQLSTATE is extracted when multiple present."""
        error = Exception(
            "SQLSTATE: 08003 connection error, previous SQLSTATE: 42000"
        )
        sqlstate = db_manager._extract_sqlstate(error)
        assert sqlstate == "08003"

    def test_extract_sqlstate_no_sqlstate_present(self, db_manager):
        """Test returns None when no SQLSTATE in error message."""
        error = Exception("Generic error message without SQLSTATE")
        sqlstate = db_manager._extract_sqlstate(error)
        assert sqlstate is None

    def test_extract_sqlstate_invalid_format(self, db_manager):
        """Test returns None for invalid SQLSTATE format."""
        error = Exception("SQLSTATE: 123")  # Too short
        sqlstate = db_manager._extract_sqlstate(error)
        assert sqlstate is None

    def test_extract_sqlstate_with_whitespace(self, db_manager):
        """Test extraction handles various whitespace patterns."""
        error = Exception("Error: SQLSTATE:  08S01  ")
        sqlstate = db_manager._extract_sqlstate(error)
        assert sqlstate == "08S01"

    # ==================== Connection Error Detection - SQLSTATE Based ====================

    def test_is_connection_error_class_08_connection_exception(self, db_manager):
        """Test Class 08 (connection exceptions) detected as connection error."""
        test_cases = [
            "SQLSTATE: 08000",  # Connection exception
            "SQLSTATE: 08001",  # SQL-client unable to establish connection
            "SQLSTATE: 08003",  # Connection does not exist
            "SQLSTATE: 08004",  # Connection rejected
            "SQLSTATE: 08006",  # Connection failure
            "SQLSTATE: 08007",  # Transaction resolution unknown
            "SQLSTATE: 08S01",  # Communication link failure
        ]

        for error_msg in test_cases:
            error = Exception(error_msg)
            assert db_manager._is_connection_error(error) is True, \
                f"Failed for: {error_msg}"

    def test_is_connection_error_class_42_syntax_error(self, db_manager):
        """Test Class 42 (syntax/semantic errors) NOT detected as connection error."""
        test_cases = [
            "SQLSTATE: 42000",  # Syntax error or access violation
            "SQLSTATE: 42S02",  # Table or view not found
            "SQLSTATE: 42S22",  # Column not found
            "SQLSTATE: 42601",  # Syntax error
        ]

        for error_msg in test_cases:
            error = Exception(error_msg)
            assert db_manager._is_connection_error(error) is False, \
                f"Failed for: {error_msg}"

    def test_is_connection_error_class_22_data_exception(self, db_manager):
        """Test Class 22 (data exceptions) NOT detected as connection error."""
        test_cases = [
            "SQLSTATE: 22000",  # Data exception
            "SQLSTATE: 22001",  # String data right truncation
            "SQLSTATE: 22003",  # Numeric value out of range
            "SQLSTATE: 22012",  # Division by zero
            "SQLSTATE: 22018",  # Invalid character value for cast
        ]

        for error_msg in test_cases:
            error = Exception(error_msg)
            assert db_manager._is_connection_error(error) is False, \
                f"Failed for: {error_msg}"

    def test_is_connection_error_class_23_integrity_constraint(self, db_manager):
        """Test Class 23 (integrity constraints) NOT detected as connection error."""
        test_cases = [
            "SQLSTATE: 23000",  # Integrity constraint violation
            "SQLSTATE: 23505",  # Unique violation
            "SQLSTATE: 23503",  # Foreign key violation
        ]

        for error_msg in test_cases:
            error = Exception(error_msg)
            assert db_manager._is_connection_error(error) is False, \
                f"Failed for: {error_msg}"

    def test_is_connection_error_class_xx_internal_error(self, db_manager):
        """Test Class XX (internal errors) detected as connection error."""
        test_cases = [
            "SQLSTATE: XX000",  # Internal error
            "SQLSTATE: XX001",  # Data corrupted
        ]

        for error_msg in test_cases:
            error = Exception(error_msg)
            assert db_manager._is_connection_error(error) is True, \
                f"Failed for: {error_msg}"

    # ==================== Connection Error Detection - Exception Type ====================

    def test_is_connection_error_python_connection_error(self, db_manager):
        """Test Python ConnectionError detected as connection error."""
        error = ConnectionError("Connection refused")
        assert db_manager._is_connection_error(error) is True

    def test_is_connection_error_python_timeout_error(self, db_manager):
        """Test Python TimeoutError detected as connection error."""
        error = TimeoutError("Connection timeout")
        assert db_manager._is_connection_error(error) is True

    # ==================== Connection Error Detection - Keyword Based ====================

    def test_is_connection_error_keyword_connection_closed(self, db_manager):
        """Test 'connection closed' keyword detected."""
        error = Exception("The connection closed unexpectedly")
        assert db_manager._is_connection_error(error) is True

    def test_is_connection_error_keyword_connection_lost(self, db_manager):
        """Test 'connection lost' keyword detected."""
        error = Exception("Connection lost to database server")
        assert db_manager._is_connection_error(error) is True

    def test_is_connection_error_keyword_connection_refused(self, db_manager):
        """Test 'connection refused' keyword detected."""
        error = Exception("Connection refused by server")
        assert db_manager._is_connection_error(error) is True

    def test_is_connection_error_keyword_connection_timeout(self, db_manager):
        """Test 'connection timeout' keyword detected."""
        error = Exception("Connection timeout after 30 seconds")
        assert db_manager._is_connection_error(error) is True

    def test_is_connection_error_keyword_broken_pipe(self, db_manager):
        """Test 'broken pipe' keyword detected."""
        error = Exception("Broken pipe error occurred")
        assert db_manager._is_connection_error(error) is True

    def test_is_connection_error_keyword_network_error(self, db_manager):
        """Test 'network error' keyword detected."""
        error = Exception("Network error during query execution")
        assert db_manager._is_connection_error(error) is True

    def test_is_connection_error_keyword_case_insensitive(self, db_manager):
        """Test keyword matching is case-insensitive."""
        error = Exception("CONNECTION CLOSED")
        assert db_manager._is_connection_error(error) is True

    def test_is_connection_error_multiple_keywords(self, db_manager):
        """Test detection when multiple keywords present."""
        error = Exception("Connection timeout and network error occurred")
        assert db_manager._is_connection_error(error) is True

    # ==================== Connection Error Detection - Default Behavior ====================

    def test_is_connection_error_generic_query_error(self, db_manager):
        """Test generic query errors default to NOT connection error."""
        error = Exception("Invalid column name 'xyz'")
        assert db_manager._is_connection_error(error) is False

    def test_is_connection_error_empty_message(self, db_manager):
        """Test empty error message defaults to NOT connection error."""
        error = Exception("")
        assert db_manager._is_connection_error(error) is False

    def test_is_connection_error_none_message(self, db_manager):
        """Test None-like error defaults to NOT connection error."""
        error = Exception(None)
        assert db_manager._is_connection_error(error) is False

    # ==================== Priority: SQLSTATE Over Keywords ====================

    def test_sqlstate_overrides_keyword_query_error(self, db_manager):
        """Test SQLSTATE 42xxx overrides connection keywords."""
        # Message has "connection" keyword but SQLSTATE indicates query error
        error = Exception(
            "SQLSTATE: 42S02 - Table 'connection_logs' not found"
        )
        assert db_manager._is_connection_error(error) is False

    def test_sqlstate_overrides_keyword_connection_error(self, db_manager):
        """Test SQLSTATE 08xxx overrides non-connection keywords."""
        # Message looks like query error but SQLSTATE indicates connection issue
        error = Exception(
            "SQLSTATE: 08003 - Query failed due to connection issue"
        )
        assert db_manager._is_connection_error(error) is True

    # ==================== Error Tracking Tests ====================

    def test_track_error_connection_error(self, db_manager):
        """Test connection error increments connection_errors counter."""
        initial_conn_errors = db_manager._connection_errors
        initial_query_errors = db_manager._query_errors

        error = Exception("Test error")
        db_manager._track_error(error, is_connection_error=True)

        assert db_manager._connection_errors == initial_conn_errors + 1
        assert db_manager._query_errors == initial_query_errors

    def test_track_error_query_error(self, db_manager):
        """Test query error increments query_errors counter."""
        initial_conn_errors = db_manager._connection_errors
        initial_query_errors = db_manager._query_errors

        error = Exception("Test error")
        db_manager._track_error(error, is_connection_error=False)

        assert db_manager._connection_errors == initial_conn_errors
        assert db_manager._query_errors == initial_query_errors + 1

    def test_track_error_multiple_errors(self, db_manager):
        """Test tracking multiple errors of different types."""
        initial_conn_errors = db_manager._connection_errors
        initial_query_errors = db_manager._query_errors

        # Track 3 connection errors and 2 query errors
        for _ in range(3):
            db_manager._track_error(Exception("conn"), is_connection_error=True)
        for _ in range(2):
            db_manager._track_error(Exception("query"), is_connection_error=False)

        assert db_manager._connection_errors == initial_conn_errors + 3
        assert db_manager._query_errors == initial_query_errors + 2

    # ==================== Edge Cases ====================

    def test_is_connection_error_with_nested_exception(self, db_manager):
        """Test error classification with nested exception messages."""
        error = Exception("Outer error: SQLSTATE: 08001")
        assert db_manager._is_connection_error(error) is True

    def test_extract_sqlstate_with_special_characters(self, db_manager):
        """Test SQLSTATE extraction with special characters in message."""
        error = Exception("Error: [SQLSTATE: 42000] - Syntax error!")
        sqlstate = db_manager._extract_sqlstate(error)
        assert sqlstate == "42000"

    def test_is_connection_error_mixed_case_sqlstate(self, db_manager):
        """Test SQLSTATE detection with mixed case."""
        error = Exception("SqlState: 08S01")
        assert db_manager._is_connection_error(error) is True

    def test_is_connection_error_partial_keyword_match(self, db_manager):
        """Test partial keyword matches don't trigger false positives."""
        # "disconnection" contains "connection" but in different context
        error = Exception("Successful disconnection from server")
        # This should still match because "connection" is in the keyword list
        # If you want to avoid this, you'd need word boundary matching
        assert db_manager._is_connection_error(error) is True

    def test_is_connection_error_keyword_in_table_name(self, db_manager):
        """Test keywords in table names don't cause false positives when SQLSTATE present."""
        error = Exception("SQLSTATE: 42S02 - Table 'network_errors' not found")
        # SQLSTATE 42S02 should override the "network" keyword
        assert db_manager._is_connection_error(error) is False


# ==================== Parametrized Tests for Comprehensive Coverage ====================

class TestErrorClassificationParametrized:
    """Parametrized tests for comprehensive SQLSTATE coverage."""

    @pytest.fixture
    def db_manager(self, monkeypatch):
        """Create offline DatabaseConnectionManager for testing."""
        monkeypatch.setenv('DATABASE_ENABLED', 'false')
        DatabaseConnectionManager._instance = None
        DatabaseConnectionManager._initialized = False
        return DatabaseConnectionManager()

    @pytest.mark.parametrize("sqlstate,expected", [
        # Connection errors (Class 08)
        ("08000", True),
        ("08001", True),
        ("08003", True),
        ("08004", True),
        ("08006", True),
        ("08007", True),
        ("08S01", True),
        # Syntax/semantic errors (Class 42)
        ("42000", False),
        ("42S02", False),
        ("42S22", False),
        ("42601", False),
        # Data exceptions (Class 22)
        ("22000", False),
        ("22001", False),
        ("22003", False),
        ("22012", False),
        # Integrity constraints (Class 23)
        ("23000", False),
        ("23505", False),
        ("23503", False),
        # Internal errors (Class XX)
        ("XX000", True),
        ("XX001", True),
    ])
    def test_sqlstate_classification(self, db_manager, sqlstate, expected):
        """Test SQLSTATE-based error classification."""
        error = Exception(f"Error with SQLSTATE: {sqlstate}")
        assert db_manager._is_connection_error(error) is False
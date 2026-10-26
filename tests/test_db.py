"""Tests for db.py - Database layer."""

from unittest.mock import MagicMock, call, patch

import pytest

from db import AMOUNT_EXPR, _connection, query


class TestAMOUNT_EXPR:
    """Test the AMOUNT_EXPR constant."""

    def test_amount_expr_is_constant(self):
        assert (
            AMOUNT_EXPR
            == "CAST(s.value_num AS DECIMAL(20,6)) / NULLIF(s.value_denom, 0)"
        )

    def test_amount_expr_prevents_float(self):
        # Verify the expression uses DECIMAL, not float
        assert "DECIMAL" in AMOUNT_EXPR
        assert "float" not in AMOUNT_EXPR.lower()

    def test_amount_expr_handles_zero_denom(self):
        # NULLIF prevents division by zero
        assert "NULLIF(s.value_denom, 0)" in AMOUNT_EXPR


class TestConnection:
    """Test database connection."""

    def test_connection_uses_read_only(self):
        with patch("mariadb.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            with _connection():
                mock_conn.cursor.assert_called_once()
                cur = mock_conn.cursor.return_value

            # Verify READ ONLY was set
            execute_calls = [call[0][0] for call in cur.execute.call_args_list]
            assert any("READ ONLY" in call for call in execute_calls)

    def test_connection_sets_statement_timeout(self):
        with patch("mariadb.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            with _connection():
                mock_conn.cursor.assert_called_once()
                cur = mock_conn.cursor.return_value

            # Verify statement timeout was set
            execute_calls = [call[0][0] for call in cur.execute.call_args_list]
            assert any("max_statement_time" in call for call in execute_calls)

    def test_connection_closes_cursor(self):
        with patch("mariadb.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            with _connection():
                cur = mock_conn.cursor.return_value
                cur.execute("SELECT 1")

            # Cursor should be closed in finally block
            assert cur.close.called

    def test_connection_closes_connection(self):
        with patch("mariadb.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            with _connection():
                pass

            # Connection should be closed in finally block
            mock_conn.close.assert_called_once()


class TestQuery:
    """Test query execution."""

    def test_query_with_params(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "test"}]

        with patch("mariadb.connect") as mock_connect:
            with patch("guard.check") as mock_guard:
                mock_guard.return_value = "SELECT * FROM accounts WHERE id = %s"
                mock_conn = MagicMock()
                mock_cursor_instance = MagicMock()
                mock_cursor_instance.fetchall.return_value = [{"id": 1, "name": "test"}]
                mock_conn.cursor.return_value = mock_cursor_instance
                mock_connect.return_value = mock_conn

                result = query("SELECT * FROM accounts WHERE id = %s", (1,))

                # execute is called 3 times: READ ONLY, timeout, and the actual query
                assert mock_cursor_instance.execute.call_count == 3
                assert mock_cursor_instance.execute.call_args_list[-1] == call(
                    "SELECT * FROM accounts WHERE id = %s", (1,)
                )
                assert result == [{"id": 1, "name": "test"}]

    def test_query_without_params(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "test"}]

        with patch("mariadb.connect") as mock_connect:
            with patch("guard.check") as mock_guard:
                mock_guard.return_value = "SELECT * FROM accounts"
                mock_conn = MagicMock()
                mock_cursor_instance = MagicMock()
                mock_cursor_instance.fetchall.return_value = [{"id": 1, "name": "test"}]
                mock_conn.cursor.return_value = mock_cursor_instance
                mock_connect.return_value = mock_conn

                result = query("SELECT * FROM accounts")

                # execute is called 3 times: READ ONLY, timeout, and the actual query
                assert mock_cursor_instance.execute.call_count == 3
                assert mock_cursor_instance.execute.call_args_list[-1] == call(
                    "SELECT * FROM accounts"
                )
                assert result == [{"id": 1, "name": "test"}]

    def test_query_returns_empty_list(self):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        with patch("mariadb.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            result = query("SELECT * FROM accounts WHERE hidden = 1")
            assert result == []

    def test_query_jsonables_bytes(self):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [{"data": b"binary_data"}]

        with patch("mariadb.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [{"data": b"binary_data"}]
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            result = query("SELECT * FROM x")
            assert result == [{"data": "binary_data"}]

    def test_query_jsonables_datetime(self):
        import datetime

        mock_result = MagicMock()
        mock_dt = datetime.datetime(2024, 1, 15, 10, 30, 0)
        mock_result.fetchall.return_value = [{"created_at": mock_dt}]

        with patch("mariadb.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [{"created_at": mock_dt}]
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            result = query("SELECT * FROM x")
            assert result == [{"created_at": "2024-01-15T10:30:00"}]

    def test_query_jsonables_date(self):
        import datetime

        mock_result = MagicMock()
        mock_date = datetime.date(2024, 1, 15)
        mock_result.fetchall.return_value = [{"date_col": mock_date}]

        with patch("mariadb.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [{"date_col": mock_date}]
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            result = query("SELECT * FROM x")
            assert result == [{"date_col": "2024-01-15"}]

    def test_guard_check_called(self):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [{"id": 1}]

        with patch("mariadb.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [{"id": 1}]
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            with patch("guard.check") as mock_guard:
                mock_guard.return_value = "SELECT 1"
                query("SELECT 1")
                mock_guard.assert_called_once_with("SELECT 1")

    def test_query_raises_on_database_error(self):
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("Database error")

        with patch("mariadb.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            with pytest.raises(Exception, match="Database error"):
                query("SELECT * FROM accounts")

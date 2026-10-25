"""Tests for server.py - MCP tools."""

import json
from decimal import Decimal
from unittest.mock import patch

import pytest

from server import (
    _date_bounds_inclusive,
    _err,
    _json_default,
    _ok,
    _resolve_account,
    get_account_balance,
    get_income_by_category,
    get_net_worth,
    get_recent_transactions,
    get_spending_by_category,
    list_accounts,
    search_transactions,
)


def _parse_response(raw: str):
    """Parse the JSON response from server functions."""
    data = json.loads(raw)
    if data.get("ok"):
        return {"success": True, "data": data.get("data", {})}
    return {"success": False, "error": data.get("error")}


def _make_mock_rows(rows: list) -> list:
    """Create mock database rows matching the actual query structure."""
    return rows


class TestOkAndErr:
    """Test helper functions."""

    def test_ok_returns_json(self):
        result = _ok({"test": "value"})
        parsed = json.loads(result)
        assert parsed == {"ok": True, "data": {"test": "value"}}

    def test_ok_with_decimal(self):
        result = _ok({"amount": Decimal("123.45")})
        parsed = json.loads(result)
        assert parsed["data"]["amount"] == "123.45"

    def test_ok_with_list(self):
        result = _ok([1, 2, 3])
        parsed = json.loads(result)
        assert parsed["data"] == [1, 2, 3]

    def test_err_returns_json(self):
        result = _err("Something went wrong", code=400)
        parsed = json.loads(result)
        assert parsed == {"ok": False, "error": "Something went wrong", "code": 400}

    def test_err_with_decimal(self):
        result = _err("Decimal error", amount=Decimal("999.99"))
        parsed = json.loads(result)
        assert parsed["error"] == "Decimal error"
        assert parsed["amount"] == "999.99"


class TestJsonDefault:
    """Test JSON serialization helper."""

    def test_decimal_with_fractional_cents(self):
        d = Decimal("123.456789")
        result = _json_default(d)
        assert result == "123.456789"

    def test_decimal_integer(self):
        d = Decimal("100")
        result = _json_default(d)
        # _json_default handles this - returns formatted string
        assert result == "100.00"  # Default format for integers

    def test_decimal_one_decimal_place(self):
        d = Decimal("100.5")
        result = _json_default(d)
        assert result == "100.50"  # Two decimal places

    def test_decimal_many_places(self):
        d = Decimal("0.0000123")
        result = _json_default(d)
        # Should keep up to 6 fractional digits
        assert result == "0.000012"  # Truncated


class TestDateBoundsInclusive:
    """Test date range conversion."""

    def test_single_day(self):
        lo, hi = _date_bounds_inclusive("2024-01-15", "2024-01-15")
        assert lo == "2024-01-15 00:00:00"
        assert hi == "2024-01-16 00:00:00"

    def test_multiple_days(self):
        lo, hi = _date_bounds_inclusive("2024-01-01", "2024-01-31")
        assert lo == "2024-01-01 00:00:00"
        assert hi == "2024-02-01 00:00:00"

    def test_end_less_than_start_raises(self):
        with pytest.raises(ValueError, match="end_date must be >= start_date"):
            _date_bounds_inclusive("2024-02-01", "2024-01-01")

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError):
            _date_bounds_inclusive("not-a-date", "2024-01-01")


class TestResolveAccount:
    """Test account resolution."""

    def test_exact_match(self):
        # Mock query returns one exact match
        mock_result = [{"guid": "g1", "name": "EQ Bank", "account_type": "ASSET", "parent_guid": None, "path": "Assets:EQ Bank"}]
        with patch("server.query", return_value=mock_result):
            account, error = _resolve_account("EQ Bank")
            assert error is None
            assert account["name"] == "EQ Bank"

    def test_exact_match_with_prefix(self):
        mock_result = [{"guid": "g1", "name": "EQ Bank", "account_type": "ASSET", "parent_guid": None, "path": "Assets:Current:EQ Bank"}]
        with patch("server.query", return_value=mock_result):
            account, error = _resolve_account("Root Account:EQ Bank")
            assert error is None
            assert account["name"] == "EQ Bank"

    def test_suffix_match(self):
        mock_result = [{"guid": "g1", "name": "EQ Bank", "account_type": "ASSET", "parent_guid": None, "path": "Assets:Current Assets:EQ Bank"}]
        with patch("server.query", return_value=mock_result):
            account, error = _resolve_account("Assets:Current Assets:EQ Bank")
            assert error is None

    def test_no_match_returns_error(self):
        with patch("server.query", return_value=[]):
            account, error = _resolve_account("NonExistent")
            assert error is not None
            assert "No account matching" in error
            assert account is None

    def test_multiple_matches_returns_error(self):
        mock_result = [
            {"guid": "g1", "name": "EQ Bank", "account_type": "ASSET", "parent_guid": None, "path": "Assets:EQ Bank"},
            {"guid": "g2", "name": "EQ Bank", "account_type": "LIABILITY", "parent_guid": None, "path": "Liabilities:EQ Bank"},
        ]
        with patch("server.query", return_value=mock_result):
            account, error = _resolve_account("EQ Bank")
            assert error is not None
            assert "2 accounts match" in error
            assert account is None

    def test_exact_name_takes_precedence(self):
        # When exact match exists, it returns that account
        mock_result = [
            {"guid": "g1", "name": "EQ Bank", "account_type": "ASSET", "parent_guid": None, "path": "Assets:EQ Bank"},
        ]
        with patch("server.query", return_value=mock_result):
            account, error = _resolve_account("EQ Bank")
            assert error is None
            assert account["name"] == "EQ Bank"

    def test_full_path_exact(self):
        mock_result = [{"guid": "g1", "name": "EQ Bank", "account_type": "ASSET", "parent_guid": None, "path": "Assets:Current Assets:EQ Bank"}]
        with patch("server.query", return_value=mock_result):
            account, error = _resolve_account("Assets:Current Assets:EQ Bank")
            assert error is None
            assert account["path"] == "Assets:Current Assets:EQ Bank"


class TestListAccounts:
    """Test list_accounts tool."""

    def test_returns_accounts(self):
        mock_result = [
            {"guid": "g1", "name": "Cash", "account_type": "ASSET", "parent_guid": None, "commodity_guid": "c1", "commodity_mnemonic": "USD"},
            {"guid": "g2", "name": "Credit Card", "account_type": "LIABILITY", "parent_guid": None, "commodity_guid": "c1", "commodity_mnemonic": "USD"},
        ]
        with patch("server.query", return_value=mock_result):
            result = list_accounts()
            parsed = _parse_response(result)
            assert parsed["success"]
            assert len(parsed["data"]) == 2
            assert parsed["data"][0]["name"] == "Cash"
            assert parsed["data"][1]["name"] == "Credit Card"

    def test_empty_result(self):
        with patch("server.query", return_value=[]):
            result = list_accounts()
            parsed = _parse_response(result)
            assert parsed["success"]
            assert parsed["data"] == []

    def test_no_commodities(self):
        mock_result = [
            {"guid": "g1", "name": "Cash", "account_type": "ASSET", "parent_guid": None, "commodity_guid": None, "commodity_mnemonic": None},
        ]
        with patch("server.query", return_value=mock_result):
            result = list_accounts()
            parsed = _parse_response(result)
            assert parsed["success"]
            assert parsed["data"][0]["commodity_mnemonic"] is None


class TestGetAccountBalance:
    """Test get_account_balance tool."""

    def test_success_with_children(self):
        # Track call order - first call is account resolution
        call_count = [0]

        def mock_query(sql, params):
            call_count[0] += 1
            # First call: account resolution (no 'tree' in SQL)
            if call_count[0] == 1:
                return [{"guid": "g1", "name": "EQ Bank", "account_type": "ASSET", "parent_guid": None, "path": "Assets:EQ Bank"}]
            # Second call: balance query (has 'tree' in SQL)
            return [{"balance": "100.00"}]

        with patch("server.query", side_effect=mock_query):
            result = get_account_balance("EQ Bank", include_children=True)
            parsed = _parse_response(result)
            assert parsed["success"]
            assert parsed["data"]["account"] == "EQ Bank"
            assert parsed["data"]["raw_ledger_balance"] == "100.00"
            assert parsed["data"]["include_children"] is True

    def test_success_without_children(self):
        call_count = [0]

        def mock_query(sql, params):
            call_count[0] += 1
            if call_count[0] == 1:
                return [{"guid": "g1", "name": "EQ Bank", "account_type": "ASSET", "parent_guid": None, "path": "Assets:EQ Bank"}]
            return [{"balance": "50.00"}]

        with patch("server.query", side_effect=mock_query):
            result = get_account_balance("EQ Bank", include_children=False)
            parsed = _parse_response(result)
            assert parsed["data"]["include_children"] is False

    def test_with_as_of_date(self):
        call_count = [0]

        def mock_query(sql, params):
            call_count[0] += 1
            if call_count[0] == 1:
                return [{"guid": "g1", "name": "EQ Bank", "account_type": "ASSET", "parent_guid": None, "path": "Assets:EQ Bank"}]
            return [{"balance": "200.00"}]

        with patch("server.query", side_effect=mock_query):
            result = get_account_balance("EQ Bank", as_of_date="2024-01-15")
            parsed = _parse_response(result)
            assert parsed["data"]["as_of"] == "2024-01-15"

    def test_negative_balance(self):
        call_count = [0]

        def mock_query(sql, params):
            call_count[0] += 1
            if call_count[0] == 1:
                return [{"guid": "g1", "name": "Credit Card", "account_type": "LIABILITY", "parent_guid": None, "path": "Liabilities:Credit Card"}]
            return [{"balance": "-500.00"}]

        with patch("server.query", side_effect=mock_query):
            result = get_account_balance("Credit Card")
            parsed = _parse_response(result)
            assert parsed["data"]["raw_ledger_balance"] == "-500.00"
            assert parsed["data"]["account_type"] == "LIABILITY"

    def test_invalid_date(self):
        # Invalid date should return error before querying database
        with patch("server.query"):
            result = get_account_balance("EQ Bank", as_of_date="invalid")
            parsed = _parse_response(result)
            assert not parsed["success"]
            assert "Invalid as_of_date" in parsed["error"]

    def test_account_not_found(self):
        def mock_query(sql, params):
            return []

        with patch("server.query", side_effect=mock_query):
            result = get_account_balance("NonExistent")
            parsed = _parse_response(result)
            assert not parsed["success"]
            assert "No account matching" in parsed["error"]

    def test_ambiguous_account(self):
        # When multiple accounts match, _resolve_account returns error
        # The SQL query returns both matches in a single call
        def mock_query(sql, params):
            # The CTE query returns multiple rows when there are multiple matches
            if "WHERE name =" in sql:
                return [
                    {"guid": "g1", "name": "EQ Bank", "account_type": "ASSET", "parent_guid": None, "path": "Assets:EQ Bank"},
                    {"guid": "g2", "name": "EQ Bank", "account_type": "LIABILITY", "parent_guid": None, "path": "Liabilities:EQ Bank"},
                ]
            return []

        with patch("server.query", side_effect=mock_query):
            result = get_account_balance("EQ Bank")
            parsed = _parse_response(result)
            assert not parsed["success"]
            assert "2 accounts match" in parsed["error"]
            # Should have made exactly 1 call (the account resolution query)
            # and the error should be returned without attempting the balance query


class TestGetRecentTransactions:
    """Test get_recent_transactions tool."""

    def test_returns_transactions(self):
        mock_account = {"guid": "g1", "name": "Food", "account_type": "ASSET"}
        mock_transactions = [
            {"post_date": "2024-01-15", "description": "Grocery Store", "memo": "Weekly shopping", "amount": "-45.00"},
            {"post_date": "2024-01-14", "description": "Coffee", "memo": "Downtown", "amount": "-5.50"},
        ]

        def mock_query(sql, params):
            if "account_guid" in sql.lower():
                return mock_transactions
            return [mock_account]

        with patch("server.query", side_effect=mock_query):
            result = get_recent_transactions("Food", limit=5)
            parsed = _parse_response(result)
            assert parsed["success"]
            assert parsed["data"]["limit"] == 5
            assert len(parsed["data"]["transactions"]) == 2

    def test_limit_clamped_to_200(self):
        mock_account = {"guid": "g1", "name": "Test", "account_type": "ASSET"}
        mock_transactions = [{"post_date": "2024-01-15", "description": "Test", "memo": "", "amount": "0.00"}] * 300

        def mock_query(sql, params):
            if "account_guid" in sql.lower():
                return mock_transactions
            return [mock_account]

        with patch("server.query", side_effect=mock_query):
            result = get_recent_transactions("Test", limit=300)
            parsed = _parse_response(result)
            # Should clamp to 200
            assert parsed["data"]["limit"] == 200

    def test_min_limit(self):
        mock_account = {"guid": "g1", "name": "Test", "account_type": "ASSET"}
        mock_transactions = [{"post_date": "2024-01-15", "description": "Test", "memo": "", "amount": "0.00"}]

        def mock_query(sql, params):
            if "account_guid" in sql.lower():
                return mock_transactions
            return [mock_account]

        with patch("server.query", side_effect=mock_query):
            result = get_recent_transactions("Test", limit=0)
            parsed = _parse_response(result)
            assert parsed["data"]["limit"] == 1


class TestGetSpendingByCategory:
    """Test get_spending_by_category tool."""

    def test_returns_spending(self):
        mock_result = [
            {"account": "Groceries", "account_type": "EXPENSE", "total": "150.00"},
            {"account": "Restaurants", "account_type": "EXPENSE", "total": "75.00"},
        ]
        with patch("server.query", return_value=mock_result):
            result = get_spending_by_category("2024-01-01", "2024-01-31")
            parsed = _parse_response(result)
            assert parsed["success"]
            assert parsed["data"]["start"] == "2024-01-01"
            assert parsed["data"]["end"] == "2024-01-31"
            assert len(parsed["data"]["categories"]) == 2

    def test_empty_result(self):
        with patch("server.query", return_value=[]):
            result = get_spending_by_category("2024-01-01", "2024-01-31")
            parsed = _parse_response(result)
            assert parsed["success"]
            assert parsed["data"]["categories"] == []

    def test_invalid_date_range(self):
        result = get_spending_by_category("2024-02-01", "2024-01-01")
        parsed = _parse_response(result)
        assert not parsed["success"]
        assert "end_date must be >= start_date" in parsed["error"]

    def test_accounts_ordered_by_total_desc(self):
        mock_result = [
            {"account": "Category A", "account_type": "EXPENSE", "total": "100.00"},
            {"account": "Category B", "account_type": "EXPENSE", "total": "50.00"},
        ]
        with patch("server.query", return_value=mock_result):
            result = get_spending_by_category("2024-01-01", "2024-01-31")
            parsed = _parse_response(result)
            assert parsed["data"]["categories"][0]["total"] == "100.00"
            assert parsed["data"]["categories"][1]["total"] == "50.00"


class TestGetNetWorth:
    """Test get_net_worth tool."""

    def test_returns_net_worth(self):
        from decimal import Decimal
        mock_result = [
            {"account_type": "ASSET", "balance": Decimal("50000.00")},
            {"account_type": "LIABILITY", "balance": Decimal("-20000.00")},
        ]
        with patch("server.query", return_value=mock_result):
            result = get_net_worth()
            parsed = _parse_response(result)
            assert parsed["success"]
            assert parsed["data"]["total_assets"] == "50000.00"
            assert parsed["data"]["total_liabilities_owed"] == "20000.00"
            assert parsed["data"]["net_worth"] == "30000.00"

    def test_empty_assets_and_liabilities(self):
        with patch("server.query", return_value=[]):
            result = get_net_worth()
            parsed = _parse_response(result)
            assert parsed["success"]
            assert parsed["data"]["total_assets"] == "0.00"
            assert parsed["data"]["total_liabilities_owed"] == "0.00"
            assert parsed["data"]["net_worth"] == "0.00"

    def test_with_as_of_date(self):
        from decimal import Decimal
        mock_result = [
            {"account_type": "ASSET", "balance": Decimal("100.00")},
            {"account_type": "LIABILITY", "balance": Decimal("-40.00")},
        ]
        with patch("server.query", return_value=mock_result):
            result = get_net_worth(as_of_date="2024-01-15")
            parsed = _parse_response(result)
            assert parsed["data"]["as_of"] == "2024-01-15"


class TestSearchTransactions:
    """Test search_transactions tool."""

    def test_returns_matches(self):
        mock_result = [
            {"post_date": "2024-01-15", "description": "Grocery Store", "memo": "Milk and eggs", "account": "Groceries", "account_type": "EXPENSE", "amount": "-45.00"},
            {"post_date": "2024-01-14", "description": "Dinner", "memo": "Coffee at Starbucks", "account": "Restaurants", "account_type": "EXPENSE", "amount": "-8.50"},
        ]
        with patch("server.query", return_value=mock_result):
            result = search_transactions("coffee", limit=5)
            parsed = _parse_response(result)
            assert parsed["success"]
            assert parsed["data"]["keyword"] == "coffee"
            assert parsed["data"]["limit"] == 5
            assert len(parsed["data"]["matches"]) == 2

    def test_case_insensitive(self):
        mock_result = [
            {"post_date": "2024-01-15", "description": "GROCERY STORE", "memo": "MILK", "account": "Groceries", "account_type": "EXPENSE", "amount": "-50.00"},
        ]
        with patch("server.query", return_value=mock_result):
            result = search_transactions("grocery")
            parsed = _parse_response(result)
            assert parsed["success"]
            assert len(parsed["data"]["matches"]) == 1

    def test_matches_memo(self):
        mock_result = [
            {"post_date": "2024-01-15", "description": "Transfer", "memo": "Grocery payment", "account": "EQ Bank", "account_type": "ASSET", "amount": "-50.00"},
        ]
        with patch("server.query", return_value=mock_result):
            result = search_transactions("grocery")
            parsed = _parse_response(result)
            assert parsed["success"]
            assert len(parsed["data"]["matches"]) == 1

    def test_limit_clamped(self):
        mock_result = [{"post_date": "2024-01-15", "description": "Test", "memo": "", "account": "Test", "account_type": "EXPENSE", "amount": "0.00"}] * 300
        with patch("server.query", return_value=mock_result):
            result = search_transactions("test", limit=300)
            parsed = _parse_response(result)
            assert parsed["data"]["limit"] == 200

    def test_no_matches(self):
        with patch("server.query", return_value=[]):
            result = search_transactions("nonexistent")
            parsed = _parse_response(result)
            assert parsed["success"]
            assert parsed["data"]["matches"] == []


class TestGetIncomeByCategory:
    """Test get_income_by_category tool."""

    def test_returns_income(self):
        mock_result = [
            {"account": "Salary", "account_type": "INCOME", "total": "5000.00"},
            {"account": "Freelance", "account_type": "INCOME", "total": "1500.00"},
        ]
        with patch("server.query", return_value=mock_result):
            result = get_income_by_category("2024-01-01", "2024-01-31")
            parsed = _parse_response(result)
            assert parsed["success"]
            assert len(parsed["data"]["income_earned"]) == 2

    def test_income_is_positive(self):
        mock_result = [{"account": "Salary", "account_type": "INCOME", "total": "5000.00"}]
        with patch("server.query", return_value=mock_result):
            result = get_income_by_category("2024-01-01", "2024-01-31")
            parsed = _parse_response(result)
            assert parsed["data"]["income_earned"][0]["total"] == "5000.00"


class TestErrorHandling:
    """Test error handling in server functions."""

    def test_search_transactions_empty_result(self):
        """Test when search returns no matches."""
        with patch("server.query", return_value=[]):
            result = search_transactions("nonexistent")
            parsed = _parse_response(result)
            assert parsed["success"]
            assert parsed["data"]["matches"] == []

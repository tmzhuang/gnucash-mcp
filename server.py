"""
Read-only Model Context Protocol server exposing GnuCash (MariaDB)
as finance tools.

Run:  python server.py            # stdio transport
"""

import datetime
import json
from decimal import Decimal

from mcp.server.mcpserver import MCPServer

from db import AMOUNT_EXPR, query

mcp = MCPServer("gnucash-readonly")


# ---------------------------------------------------------------------------
# Response envelope + JSON helpers
# ---------------------------------------------------------------------------

def _json_default(o):
    if isinstance(o, Decimal):
        # If it has fractional cents, keep up to 6 digits. Otherwise, 2.
        s = f"{o:.6f}".rstrip('0')
        if s.endswith('.'):
            s += '00'
        elif len(s.split('.')[1]) == 1:
            s += '0'
        return s
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _ok(data):
    return json.dumps({"ok": True, "data": data}, indent=2, default=_json_default)


def _err(msg, **extra):
    return json.dumps(
        {"ok": False, "error": msg, **extra}, indent=2, default=_json_default
    )


# ---------------------------------------------------------------------------
# Account-name resolution
# ---------------------------------------------------------------------------

def _resolve_account(name: str):
    """Resolve a user-supplied account identifier to exactly one account.

    Accepts:
      * a colon-separated path, exact or suffix, e.g.
        'Assets:Current Assets:Angie:EQ Bank' or 'Angie:EQ Bank'
        (optionally prefixed with 'Root Account:'),
      * or a leaf-name substring, e.g. 'EQ Bank'.
    """
    cleaned = name.strip()
    if cleaned.lower().startswith("root account:"):
        cleaned = cleaned[len("root account:"):].strip()

    base_sql = """
    WITH RECURSIVE tree AS (
        SELECT a.guid, a.name, a.account_type, a.parent_guid,
               CAST(a.name AS CHAR(2000)) AS path
        FROM accounts a
        JOIN accounts p ON p.guid = a.parent_guid
        WHERE p.account_type = 'ROOT' AND a.hidden = 0
        UNION ALL
        SELECT a.guid, a.name, a.account_type, a.parent_guid,
               CONCAT(t.path, ':', a.name)
        FROM accounts a
        JOIN tree t ON a.parent_guid = t.guid
        WHERE a.hidden = 0
    )
    SELECT guid, name, account_type, parent_guid, path
    FROM tree
    """

    if ":" in cleaned:
        # Exact path OR any path ending with ':<input>'.
        rows = query(
            base_sql
            + " WHERE path = %s OR path LIKE CONCAT('%:', %s) ORDER BY path",
            (cleaned, cleaned),
        )
    else:
        # 1. Try an EXACT name match first.
        rows = query(base_sql + " WHERE name = %s", (cleaned,))

        # 2. If no exact match, fall back to substring match.
        if not rows:
            rows = query(base_sql + " WHERE name LIKE %s ORDER BY path", (f"%{cleaned}%",))

    if not rows:
        return None, _err(f"No account matching {name!r}")
    if len(rows) > 1:
        return None, _err(
            f"{len(rows)} accounts match {name!r}; "
            f"pass a full path (e.g. 'Assets:Current Assets:Angie:EQ Bank')",
            candidates=rows,
        )
    return rows[0], None


def _date_bounds_inclusive(start_iso: str, end_iso: str):
    """ISO date range -> half-open [start, end+1d) GnuCash CHAR(14) strings."""
    start = datetime.date.fromisoformat(start_iso)
    end = datetime.date.fromisoformat(end_iso)
    if end < start:
        raise ValueError("end_date must be >= start_date")
    lo = start.strftime("%Y-%m-%d %H:%M:%S")
    hi = (end + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    return lo, hi

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_accounts() -> str:
    """List every non-hidden account in the GnuCash book.

    Returns:
        A JSON-encoded string. On success, the payload is:
        `{"ok": true, "data": [{"guid": "...", "name": "...", "account_type": "ASSET", ...}, ...]}`
        The array has the form {guid, name, account_type, parent_guid,
        commodity_guid, commodity_mnemonic}. `account_type` is one of
        ASSET/LIABILITY/EQUITY/INCOME/EXPENSE.

        Account names are not guaranteed unique; the guid is authoritative.
    """
    rows = query(
        """
        SELECT a.guid,
               a.name,
               a.account_type,
               a.parent_guid,
               a.commodity_guid,
               c.mnemonic AS commodity_mnemonic
        FROM accounts a
        LEFT JOIN commodities c ON c.guid = a.commodity_guid
        WHERE a.hidden = 0
        ORDER BY a.account_type, a.name
        """
    )
    return _ok(rows)


@mcp.tool()
def get_account_balance(
    account_name: str,
    as_of_date: str | None = None,
    include_children: bool = True,
) -> str:
    """Compute the balance of an account, optionally rolling up descendants.

    Args:
        account_name: Substring match against account names. Must match one account.
        as_of_date:   ISO 'YYYY-MM-DD' (inclusive). Omit for "as of today".
        include_children: If True (default), sum splits for this account and
                          every descendant in the account tree.

    IMPORTANT SIGN CONVENTION:
    This returns the raw GnuCash balance.
    - ASSET and EXPENSE accounts are positive.
    - LIABILITY and INCOME accounts are NEGATIVE.
    (e.g., a credit card with a $500 balance will return "-500.00").
    Use the `get_net_worth` tool for human-readable totals.

    Returns:
        A JSON-encoded string. On success, the payload is:
        `{"ok": true, "data": {"account": "EQ Bank", "raw_ledger_balance": "-42.50", ...}}`

        Note: The balance is returned as a decimal string to preserve exact precision.
    """
    acct, err = _resolve_account(account_name)
    if err is not None:
        return err

    try:
        bound = None
        if as_of_date:
            bound = (
                datetime.date.fromisoformat(as_of_date) + datetime.timedelta(days=1)
            ).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return _err(f"Invalid as_of_date {as_of_date!r}; expected YYYY-MM-DD")

    if include_children:
        sql = f"""
        WITH RECURSIVE tree AS (
            SELECT guid FROM accounts WHERE guid = %s
            UNION ALL
            SELECT a.guid FROM accounts a JOIN tree t ON a.parent_guid = t.guid
        )
        SELECT COALESCE(SUM({AMOUNT_EXPR}), 0) AS balance
        FROM splits s
        JOIN transactions tx ON tx.guid = s.tx_guid
        WHERE s.account_guid IN (SELECT guid FROM tree)
          {"AND tx.post_date < %s" if bound else ""}
        """
        params = (acct["guid"], bound) if bound else (acct["guid"],)
    else:
        sql = f"""
        SELECT COALESCE(SUM({AMOUNT_EXPR}), 0) AS balance
        FROM splits s
        JOIN transactions tx ON tx.guid = s.tx_guid
        WHERE s.account_guid = %s
          {"AND tx.post_date < %s" if bound else ""}
        """
        params = (acct["guid"], bound) if bound else (acct["guid"],)

    rows = query(sql, params)
    return _ok({
        "account": acct["name"],
        "account_type": acct["account_type"],
        "raw_ledger_balance": rows[0]["balance"],
        "as_of": as_of_date or "today",
        "include_children": include_children
    })


@mcp.tool()
def get_recent_transactions(account_name: str, limit: int = 20) -> str:
    """Return the most recent transactions touching a specific account.

    Args:
        account_name: Substring match against account names. Must match one account.
        limit: Max rows to return (clamped to 1..200).

    Each row: {post_date, description, memo, amount}. `amount` is the signed
    amount on this account's side of the split (decimal string, e.g. "-42.50").

    Returns:
        A JSON-encoded string. On success, the payload is:
        `{"ok": true, "data": {"start": "2024-08-01", "end": "2024-08-31", "categories": [{"account": "Groceries", "total": "150.00"}, ...]}}`

        `total` is a decimal string (positive = spending).
    """
    acct, err = _resolve_account(account_name)
    if err is not None:
        return err
    limit = max(1, min(int(limit), 200))

    rows = query(
        f"""
        SELECT tx.post_date,
               tx.description,
               s.memo,
               {AMOUNT_EXPR} AS amount
        FROM splits s
        JOIN transactions tx ON tx.guid = s.tx_guid
        WHERE s.account_guid = %s
        ORDER BY tx.post_date DESC, tx.guid DESC
        LIMIT %s
        """,
        (acct["guid"], limit),
    )
    return _ok({"account": acct["name"], "limit": limit, "transactions": rows})


@mcp.tool()
def get_spending_by_category(start_date: str, end_date: str) -> str:
    """Aggregate EXPENSE-account spending over an inclusive date range.

    Args:
        start_date: ISO 'YYYY-MM-DD' (inclusive).
        end_date:   ISO 'YYYY-MM-DD' (inclusive).

    Returns one row per expense account with a non-zero total:
    {account, account_type, total}. `total` is a decimal string (positive =
    spending, per GnuCash's expense sign convention).
    """
    try:
        lo, hi = _date_bounds_inclusive(start_date, end_date)
    except ValueError as e:
        return _err(str(e))

    rows = query(
        f"""
        SELECT a.name AS account,
               a.account_type,
               SUM({AMOUNT_EXPR}) AS total
        FROM splits s
        JOIN transactions tx ON tx.guid = s.tx_guid
        JOIN accounts a ON a.guid = s.account_guid
        WHERE a.account_type = 'EXPENSE'
          AND a.hidden = 0
          AND tx.post_date >= %s
          AND tx.post_date < %s
        GROUP BY a.guid, a.name, a.account_type
        HAVING total <> 0
        ORDER BY total DESC
        """,
        (lo, hi),
    )
    return _ok({"start": start_date, "end": end_date, "categories": rows})


@mcp.tool()
def search_transactions(keyword: str, limit: int = 20) -> str:
    """Search transaction descriptions and split memos (case-insensitive substring).

    Args:
        keyword: Substring to match against transactions.description or splits.memo.
        limit: Max rows to return (clamped to 1..200).

    Returns:
        A JSON-encoded string. On success, the payload is:
        `{"ok": true, "data": {"keyword": "grocery", "matches": [{"post_date": "...", "description": "...", "account": "...", "amount": "-42.50"}, ...]}}`

    Each row is one split, so a single transaction appears once per account
    it touches: {post_date, description, memo, account, account_type, amount}.
    """
    limit = max(1, min(int(limit), 200))
    pattern = f"%{keyword}%"

    rows = query(
        f"""
        SELECT tx.post_date,
               tx.description,
               s.memo,
               a.name AS account,
               a.account_type,
               {AMOUNT_EXPR} AS amount
        FROM splits s
        JOIN transactions tx ON tx.guid = s.tx_guid
        JOIN accounts a ON a.guid = s.account_guid
        WHERE a.hidden = 0
          AND (tx.description LIKE %s OR s.memo LIKE %s)
        ORDER BY tx.post_date DESC, tx.guid DESC
        LIMIT %s
        """,
        (pattern, pattern, limit),
    )
    return _ok({"keyword": keyword, "limit": limit, "matches": rows})


@mcp.tool()
def get_net_worth(as_of_date: str | None = None) -> str:
    """Calculate total net worth (Total Assets - Total Liabilities).

    Args:
        as_of_date: ISO 'YYYY-MM-DD' (inclusive). Omit for "as of today".

    Returns:
        A JSON-encoded string. On success, the payload is:
        `{"ok": true, "data": {"as_of": "today", "total_assets": "496838.74", "total_liabilities_owed": "222085.39", "net_worth": "274753.35"}}`


    Returns a summary including total_assets, total_liabilities, and net_worth.
    All amounts are positive decimal strings for easy reading.
    """
    try:
        bound = None
        if as_of_date:
            bound = (
                datetime.date.fromisoformat(as_of_date) + datetime.timedelta(days=1)
            ).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return _err(f"Invalid as_of_date {as_of_date!r}; expected YYYY-MM-DD")

    sql = f"""
    SELECT a.account_type,
           COALESCE(SUM({AMOUNT_EXPR}), 0) AS balance
    FROM splits s
    JOIN transactions tx ON tx.guid = s.tx_guid
    JOIN accounts a ON a.guid = s.account_guid
    WHERE a.account_type IN ('ASSET', 'LIABILITY')
      AND a.hidden = 0
      {"AND tx.post_date < %s" if bound else ""}
    GROUP BY a.account_type
    """

    params = (bound,) if bound else ()
    rows = query(sql, params)

    # Map the results. GnuCash stores liabilities as negative numbers.
    balances = {row["account_type"]: row["balance"] for row in rows}

    total_assets = balances.get("ASSET", Decimal(0))

    # Convert GnuCash's negative liability balance to a positive amount owed
    total_liabilities_raw = balances.get("LIABILITY", Decimal(0))
    total_liabilities = abs(total_liabilities_raw)

    net_worth = total_assets - total_liabilities

    return _ok({
        "as_of": as_of_date or "today",
        "total_assets": total_assets,
        "total_liabilities_owed": total_liabilities,
        "net_worth": net_worth,
        "note": "In GnuCash, liabilities are stored as negative numbers. This tool returns the absolute value of what you owe."
    })


@mcp.tool()
def get_income_by_category(start_date: str, end_date: str) -> str:
    """Aggregate INCOME-account earnings over an inclusive date range.

    Args:
        start_date: ISO 'YYYY-MM-DD' (inclusive).
        end_date:   ISO 'YYYY-MM-DD' (inclusive).

    Returns one row per income account with a non-zero total:
    {account, account_type, total}. `total` is a positive decimal string
    (e.g. "1500.00").

    Returns:
        A JSON-encoded string. On success, the payload is:
        `{"ok": true, "data": {"start": "2024-08-01", "end": "2024-08-31", "income_earned": [{"account": "Salary", "total": "5000.00"}, ...]}}`
        `total` is a positive decimal string.
    """
    try:
        lo, hi = _date_bounds_inclusive(start_date, end_date)
    except ValueError as e:
        return _err(str(e))

    rows = query(
        f"""
        SELECT a.name AS account,
               a.account_type,
               ABS(SUM({AMOUNT_EXPR})) AS total
        FROM splits s
        JOIN transactions tx ON tx.guid = s.tx_guid
        JOIN accounts a ON a.guid = s.account_guid
        WHERE a.account_type = 'INCOME'
          AND a.hidden = 0
          AND tx.post_date >= %s
          AND tx.post_date < %s
        GROUP BY a.guid, a.name, a.account_type
        HAVING total <> 0
        ORDER BY total DESC
        """,
        (lo, hi),
    )
    return _ok({
        "start": start_date,
        "end": end_date,
        "income_earned": rows,
        "note": "In GnuCash, income is stored as negative numbers. This tool returns positive absolute values for readability."
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")

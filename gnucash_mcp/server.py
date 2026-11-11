"""
Read-only Model Context Protocol server exposing GnuCash (MariaDB)
as finance tools.

Run:  python server.py            # stdio transport
"""

import calendar
import datetime
import json
from decimal import Decimal

from mcp.server.mcpserver import MCPServer

from .db import AMOUNT_EXPR, query

mcp = MCPServer("gnucash-readonly")


# ---------------------------------------------------------------------------
# Response envelope + JSON helpers
# ---------------------------------------------------------------------------


def _json_default(o):
    if isinstance(o, Decimal):
        # If it has fractional cents, keep up to 6 digits. Otherwise, 2.
        s = f"{o:.6f}".rstrip("0")
        if s.endswith("."):
            s += "00"
        elif len(s.split(".")[1]) == 1:
            s += "0"
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
        cleaned = cleaned[len("root account:") :].strip()

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
            base_sql + " WHERE path = %s OR path LIKE CONCAT('%:', %s) ORDER BY path",
            (cleaned, cleaned),
        )
    else:
        # 1. Try an EXACT name match first.
        rows = query(base_sql + " WHERE name = %s", (cleaned,))

        # 2. If no exact match, fall back to substring match.
        if not rows:
            rows = query(
                base_sql + " WHERE name LIKE %s ORDER BY path", (f"%{cleaned}%",)
            )

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
    """ISO date range -> half-open [start, end+1d) datetime strings."""
    start = datetime.date.fromisoformat(start_iso)
    end = datetime.date.fromisoformat(end_iso)
    if end < start:
        raise ValueError("end_date must be >= start_date")
    lo = start.strftime("%Y-%m-%d %H:%M:%S")
    hi = (end + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    return lo, hi


@mcp.tool()
def get_all_transactions_range() -> str:
    """Return the earliest and latest transaction dates across all accounts.

    Returns:
        A JSON-encoded string with {earliest, latest} as ISO 'YYYY-MM-DD' date strings.
        If no transactions exist, both are null.
    """
    rows = query("""
        SELECT MIN(tx.post_date) AS earliest,
               MAX(tx.post_date) AS latest
        FROM transactions tx
        WHERE EXISTS (
            SELECT 1 FROM splits s WHERE s.tx_guid = tx.guid
        )
    """)
    row = rows[0]
    return _ok(
        {
            "earliest": row["earliest"][:10] if row["earliest"] else None,
            "latest": row["latest"][:10] if row["latest"] else None,
        }
    )


@mcp.tool()
def get_transaction_count_by_year() -> str:
    """Return the number of distinct transactions per calendar year.

    Returns:
        A JSON-encoded string with {years: [{year, txn_count}, ...]}.
        Only years with at least one transaction are included, ordered oldest first.
    """
    rows = query("""
        SELECT YEAR(tx.post_date) AS year,
               COUNT(DISTINCT tx.guid) AS txn_count
        FROM transactions tx
        WHERE EXISTS (
            SELECT 1 FROM splits s WHERE s.tx_guid = tx.guid
        )
        GROUP BY YEAR(tx.post_date)
        ORDER BY year
    """)
    result = [{"year": int(r["year"]), "txn_count": int(r["txn_count"])} for r in rows]
    return _ok({"years": result})


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


VALID_ACCOUNT_TYPES = frozenset({"ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"})


@mcp.tool()
def list_accounts(account_type: str | None = None) -> str:
    """List every non-hidden account in the GnuCash book, optionally filtered by type.

    Args:
        account_type: Filter to a single account type (ASSET, LIABILITY, EQUITY,
                      INCOME, EXPENSE). Omit for all types.

    Returns:
        A JSON-encoded string. On success, the payload is:
        `{\"ok\": true, \"data\": [{\"guid\": \"...\", \"name\": \"...\", \"account_type\": \"ASSET\", ...}, ...]}`
        The array has the form {guid, name, account_type, parent_guid,
        commodity_guid, commodity_mnemonic}. `account_type` is one of
        ASSET/LIABILITY/EQUITY/INCOME/EXPENSE.

        Account names are not guaranteed unique; the guid is authoritative.
    """
    if account_type is not None:
        upper = account_type.upper()
        if upper not in VALID_ACCOUNT_TYPES:
            return _err(
                f"Invalid account_type {account_type!r}. "
                f"Must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"
            )
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
              AND a.account_type = %s
            ORDER BY a.name
            """,
            (upper,),
        )
    else:
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
    return _ok(
        {
            "account": acct["name"],
            "account_type": acct["account_type"],
            "raw_ledger_balance": rows[0]["balance"],
            "as_of": as_of_date or "today",
            "include_children": include_children,
        }
    )


@mcp.tool()
def get_recent_transactions(
    account_name: str,
    limit: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
    order_direction: str = "DESC",
) -> str:
    """Return transactions touching a specific account, with optional date filtering.

    Args:
        account_name: Substring match against account names. Must match one account.
        limit: Max rows to return (clamped to 1..200).
        start_date: ISO 'YYYY-MM-DD' (inclusive). Omit for no lower bound.
        end_date:   ISO 'YYYY-MM-DD' (inclusive). Omit for no upper bound.
        order_direction: 'DESC' (default, newest first) or 'ASC' (oldest first).

    Each row: {post_date, description, memo, amount}. `amount` is the signed
    amount on this account's side of the split (decimal string, e.g. "-42.50").

    Returns:
        A JSON-encoded string. On success, the payload is:
        `{"ok": true, "data": {"account": "...", "limit": 20, "transactions": [...]}}`
    """
    acct, err = _resolve_account(account_name)
    if err is not None:
        return err
    limit = max(1, min(int(limit), 200))

    try:
        date_params = []
        date_clauses = ""
        if start_date or end_date:
            lo, hi = _date_bounds_inclusive(
                start_date or "1900-01-01",
                end_date or "2999-12-31",
            )
            date_clauses = "AND tx.post_date >= %s AND tx.post_date < %s"
            date_params = [lo, hi]
    except ValueError as e:
        return _err(str(e))

    order_dir = "ASC" if order_direction.upper() == "ASC" else "DESC"

    rows = query(
        f"""
        SELECT tx.post_date,
               tx.description,
               s.memo,
               {AMOUNT_EXPR} AS amount
        FROM splits s
        JOIN transactions tx ON tx.guid = s.tx_guid
        WHERE s.account_guid = %s
          {date_clauses}
        ORDER BY tx.post_date {order_dir}, tx.guid {order_dir}
        LIMIT %s
        """,
        (acct["guid"], *date_params, limit),
    )
    return _ok(
        {
            "account": acct["name"],
            "limit": limit,
            "start_date": start_date,
            "end_date": end_date,
            "order_direction": order_dir,
            "transactions": rows,
        }
    )


@mcp.tool()
def get_spending_by_category(
    start_date: str,
    end_date: str,
    account_type: str | None = None,
    include_root: bool = False,
) -> str:
    """Aggregate spending by account over an inclusive date range.

    Args:
        start_date: ISO 'YYYY-MM-DD' (inclusive).
        end_date:   ISO 'YYYY-MM-DD' (inclusive).
        account_type: Account type to filter by (default "EXPENSE").
            Valid types: ASSET, EQUITY, EXPENSE, INCOME, LIABILITY.
        include_root: If True, return full path from Expenses root
            (e.g. 'Expenses:Auto:Fuel'). If False, return relative path
            (e.g. 'Auto:Fuel'). Backward-compatible default is leaf name only.

    Returns one row per account with a non-zero total:
    {account, account_type, total}. `total` is a decimal string (positive =
    spending, per GnuCash's expense sign convention).
    """
    if account_type is None:
        account_type = "EXPENSE"
    upper = account_type.upper()
    if upper not in VALID_ACCOUNT_TYPES:
        return _err(
            f"Invalid account_type {account_type!r}. "
            f"Must be one of: {', '.join(sorted(VALID_ACCOUNT_TYPES))}"
        )

    try:
        lo, hi = _date_bounds_inclusive(start_date, end_date)
    except ValueError as e:
        return _err(str(e))

    # Build the query based on include_root.
    if include_root:
        # Recursive CTE builds path from Expenses root; strip 'Expenses:' prefix.
        name_expr = "SUBSTR(tree.path, LENGTH('Expenses') + 2)"
        tree_cte = """
        WITH RECURSIVE tree AS (
            SELECT guid, name, account_type, hidden, CAST(name AS CHAR(2000)) AS path
            FROM accounts
            WHERE name = 'Expenses'
              AND parent_guid = (
                  SELECT guid FROM accounts
                  WHERE name = 'Root Account' AND account_type = 'ROOT'
              )
            UNION ALL
            SELECT a.guid, a.name, a.account_type, a.hidden, CONCAT(t.path, ':', a.name)
            FROM accounts a JOIN tree t ON a.parent_guid = t.guid
        )
        """
        from_clause = "splits s\n        JOIN transactions tx ON tx.guid = s.tx_guid\n        JOIN tree ON tree.guid = s.account_guid"
        acct_col = "tree"
    else:
        name_expr = "a.name"
        tree_cte = ""
        from_clause = "splits s\n        JOIN transactions tx ON tx.guid = s.tx_guid\n        JOIN accounts a ON a.guid = s.account_guid"
        acct_col = "a"

    rows = query(
        f"""
        {tree_cte}
        SELECT {name_expr} AS account,
               {acct_col}.account_type,
               SUM({AMOUNT_EXPR}) AS total
        FROM {from_clause}
        WHERE {acct_col}.account_type = %s
          AND {acct_col}.hidden = 0
          AND tx.post_date >= %s
          AND tx.post_date < %s
        GROUP BY {name_expr}, {acct_col}.account_type, {name_expr}
        HAVING total <> 0
        ORDER BY total DESC
        """,
        (upper, lo, hi),
    )
    return _ok({"start": start_date, "end": end_date, "categories": rows})


@mcp.tool()
def search_transactions(
    keyword: str,
    limit: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
    order_direction: str = "DESC",
) -> str:
    """Search transaction descriptions and split memos (case-insensitive substring).

    Args:
        keyword: Substring to match against transactions.description or splits.memo.
        limit: Max rows to return (clamped to 1..200).
        start_date: ISO 'YYYY-MM-DD' (inclusive). Omit for no lower bound.
        end_date:   ISO 'YYYY-MM-DD' (inclusive). Omit for no upper bound.
        order_direction: 'DESC' (default, newest first) or 'ASC' (oldest first).

    Returns:
        A JSON-encoded string. On success, the payload is:
        `{"ok": true, "data": {"keyword": "grocery", "matches": [{"post_date": "...", "description": "...", "account": "...", "amount": "-42.50"}, ...]}}`

    Each row is one split, so a single transaction appears once per account
    it touches: {post_date, description, memo, account, account_type, amount}.
    """
    limit = max(1, min(int(limit), 200))
    pattern = f"%{keyword}%"

    try:
        date_params = []
        date_clauses = ""
        if start_date or end_date:
            lo, hi = _date_bounds_inclusive(
                start_date or "1900-01-01",
                end_date or "2999-12-31",
            )
            date_clauses = "AND tx.post_date >= %s AND tx.post_date < %s"
            date_params = [lo, hi]
    except ValueError as e:
        return _err(str(e))

    order_dir = "ASC" if order_direction.upper() == "ASC" else "DESC"

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
          {date_clauses}
        ORDER BY tx.post_date {order_dir}, tx.guid {order_dir}
        LIMIT %s
        """,
        (pattern, pattern, *date_params, limit),
    )
    return _ok(
        {
            "keyword": keyword,
            "limit": limit,
            "start_date": start_date,
            "end_date": end_date,
            "order_direction": order_dir,
            "matches": rows,
        }
    )


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

    return _ok(
        {
            "as_of": as_of_date or "today",
            "total_assets": total_assets,
            "total_liabilities_owed": total_liabilities,
            "net_worth": net_worth,
            "note": "In GnuCash, liabilities are stored as negative numbers. This tool returns the absolute value of what you owe.",
        }
    )


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
    return _ok(
        {
            "start": start_date,
            "end": end_date,
            "income_earned": rows,
            "note": "In GnuCash, income is stored as negative numbers. This tool returns positive absolute values for readability.",
        }
    )


# ---------------------------------------------------------------------------
# Budget variance tool
# ---------------------------------------------------------------------------


def _budget_period_bounds(period_start, period_type, mult, num_periods):
    """Compute [(start, end)] for every period of a budget.

    Mirrors GnuCash's recurrence pacing (month/year with day-clamping).
    """
    if isinstance(period_start, str):
        ps = datetime.date.fromisoformat(period_start)
    else:
        ps = period_start

    bounds = []
    for p in range(num_periods):
        offset = p * mult
        if period_type == "year":
            start = datetime.date(ps.year + offset, ps.month, ps.day)
            nxt = datetime.date(ps.year + (offset + 1), ps.month, ps.day)
        elif period_type == "month":
            m = ps.month - 1 + offset
            sy, sm = ps.year + m // 12, m % 12 + 1
            try:
                start = datetime.date(sy, sm, ps.day)
            except ValueError:
                last_day = calendar.monthrange(sy, sm)[1]
                start = datetime.date(sy, sm, min(ps.day, last_day))

            m2 = ps.month - 1 + (offset + 1)
            ey, em = ps.year + m2 // 12, m2 % 12 + 1
            try:
                nxt = datetime.date(ey, em, ps.day)
            except ValueError:
                last_day = calendar.monthrange(ey, em)[1]
                nxt = datetime.date(ey, em, min(ps.day, last_day))
        else:
            # Fallback: skip unknown period types
            continue

        bounds.append(
            (
                start.strftime("%Y-%m-%d"),
                (nxt - datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
            )
        )
    return bounds


@mcp.tool()
def get_budget_variance(
    budget_name: str,
    period: str | int | None = None,
    account: str | None = None,
) -> str:
    """Return budget vs actual spending for a given budget.

    Args:
        budget_name: Name of the budget to evaluate (e.g. '2024 Budget').
        period: Which period(s) to report — ``None`` (current), int 0-11,
                'q1'-'q4', 'ytd', or 'all' (default: current period).
        account: Optional filter to one account name substring.

    Returns:
        A JSON-encoded string with per-account breakdown: budgeted, actual,
        remaining, percent_used. Over-budget categories are marked with a ⚠.
    """
    # 1. Resolve budget name → recurrence info
    rows = query(
        """
        SELECT b.guid, b.name, b.num_periods,
               r.recurrence_period_type, r.recurrence_mult,
               r.recurrence_period_start
        FROM budgets b
        JOIN recurrences r ON r.obj_guid = b.guid
        WHERE b.name = %s
    """,
        (budget_name,),
    )
    if not rows:
        return _err(f"Budget {budget_name!r} not found")
    budget = rows[0]

    # 2. Compute all period bounds
    all_bounds = _budget_period_bounds(
        budget["recurrence_period_start"],
        budget["recurrence_period_type"],
        budget["recurrence_mult"],
        budget["num_periods"],
    )

    # 3. Select which periods to report
    if period is None:
        # Current period: find the period whose start <= today < end
        today = datetime.date.today()
        current_idx = None
        for i, (ps, pe) in enumerate(all_bounds):
            if ps <= today.strftime("%Y-%m-%d") <= pe:
                current_idx = i
                break
        if current_idx is None:
            return _err(
                f"No active period found for budget {budget_name!r}. "
                f"Periods span {all_bounds[0][0]} to {all_bounds[-1][1]}. "
                f"Try specifying a period explicitly."
            )
        selected_periods = [current_idx]
    elif isinstance(period, int):
        if 0 <= period < len(all_bounds):
            selected_periods = [period]
        else:
            return _err(
                f"Invalid period {period}. Budget has {len(all_bounds)} periods (0-{len(all_bounds)-1})."
            )
    elif isinstance(period, str):
        p_upper = period.upper()
        if p_upper == "ALL":
            selected_periods = list(range(len(all_bounds)))
        elif p_upper == "YTD":
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            # Include all periods whose start <= today
            selected_periods = [
                i for i, (ps, pe) in enumerate(all_bounds) if ps <= today_str
            ]
        elif p_upper in ("Q1", "Q2", "Q3", "Q4"):
            q_map = {
                "Q1": range(0, 3),
                "Q2": range(3, 6),
                "Q3": range(6, 9),
                "Q4": range(9, 12),
            }
            selected_periods = [i for i in q_map[p_upper] if i < len(all_bounds)]
        else:
            return _err(
                f"Invalid period {period!r}. Use int (0-{len(all_bounds)-1}), "
                f"'all', 'ytd', or 'q1'-'q4'."
            )
    else:
        return _err(f"Invalid period type: {type(period).__name__}")

    # 4. Compute combined date range for actuals lookup
    all_dates = []
    for idx in selected_periods:
        ps, pe = all_bounds[idx]
        all_dates.append((ps, pe))

    if not all_dates:
        return _err("No periods selected")

    # 5. Get budget amounts per account for selected periods
    date_params = []
    for ps, pe in all_dates:
        date_params.extend([ps, pe])

    budget_sql = f"""
        SELECT ba.account_guid, a.name AS account_name, a.account_type,
               SUM(ba.amount_num / NULLIF(ba.amount_denom, 0)) AS total_budgeted
        FROM budget_amounts ba
        JOIN accounts a ON a.guid = ba.account_guid
        WHERE ba.budget_guid = %s
          AND (ba.period_num IN ({', '.join(str(i) for i in selected_periods)}))
        GROUP BY ba.account_guid, a.name, a.account_type
    """

    budget_rows = query(budget_sql, (budget["guid"],))
    budget_by_account = {r["account_guid"]: r for r in budget_rows}

    # 6. Get actual spending per account within the date range
    if all_dates:
        # Build OR conditions for each period's date range
        or_clauses = " OR ".join(
            ["(tx.post_date >= %s AND tx.post_date < %s)" for _, _ in all_dates]
        )
        actual_params = []
        for ps, pe in all_dates:
            actual_params.extend([ps + " 00:00:00", pe + " 23:59:59"])

        # Resolve matching account GUIDs (for both budget and actual filtering)
        matched_guids = []
        if account is not None:
            acct_rows = query(
                """
                SELECT a.guid FROM accounts a
                WHERE a.hidden = 0 AND a.name LIKE %s
            """,
                (f"%{account}%",),
            )
            matched_guids = [r["guid"] for r in acct_rows]

        # Filter budget rows by matched accounts if specified
        if matched_guids:
            guid_set = set(matched_guids)
            budget_by_account = {
                k: v for k, v in budget_by_account.items() if k in guid_set
            }

        # Filter actual spending query by matched accounts
        account_filter_sql = ""
        if matched_guids:
            acc_guids = ", ".join(["%s"] * len(matched_guids))
            account_filter_sql = f" AND s.account_guid IN ({acc_guids})"
            actual_params.extend(matched_guids)

        actual_sql = f"""
            SELECT s.account_guid, a.name AS account_name, a.account_type,
                   SUM({AMOUNT_EXPR}) AS total_actual
            FROM splits s
            JOIN transactions tx ON tx.guid = s.tx_guid
            JOIN accounts a ON a.guid = s.account_guid
            WHERE a.account_type = 'EXPENSE'
              AND a.hidden = 0
              AND ({or_clauses})
              {account_filter_sql}
            GROUP BY s.account_guid, a.name, a.account_type
            HAVING total_actual <> 0
        """

        actual_rows = query(actual_sql, tuple(actual_params))
    else:
        actual_rows = []

    # Build name lookups from both budget and actual rows
    account_names = {}
    for r in budget_rows:
        account_names[r["account_guid"]] = r["account_name"]
    for r in actual_rows:
        if r["account_guid"] not in account_names:
            account_names[r["account_guid"]] = r["account_name"]

    actual_by_account = {}
    for r in actual_rows:
        guid = r["account_guid"]
        if guid not in actual_by_account:
            actual_by_account[guid] = Decimal("0")
        actual_by_account[guid] += Decimal(str(r["total_actual"]))

    # 7. Combine and format results
    all_guids = set(budget_by_account.keys()) | set(actual_by_account.keys())
    results = []
    for guid in sorted(all_guids):
        b = budget_by_account.get(guid, {})
        a = actual_by_account.get(guid, Decimal("0"))
        budgeted = Decimal(str(b.get("total_budgeted", 0)))
        name = account_names.get(guid, "Unknown")

        remaining = budgeted - a
        if budgeted != 0:
            pct_used = float(a / budgeted * 100)
        else:
            pct_used = 0.0 if a == 0 else None

        entry = {
            "account": name,
            "budgeted": str(budgeted),
            "actual": str(a),
            "remaining": str(remaining),
            "percent_used": round(pct_used, 1) if pct_used is not None else None,
            "over_budget": pct_used is not None and pct_used > 100,
        }
        results.append(entry)

    # Format period description
    if len(selected_periods) == 1:
        idx = selected_periods[0]
        ps, pe = all_bounds[idx]
        s = datetime.date.fromisoformat(ps)
        e = datetime.date.fromisoformat(pe)
        period_desc = f"{s.strftime('%b %d')} - {e.strftime('%b %d, %Y')}"
    else:
        first_ps, last_pe = (
            all_bounds[selected_periods[0]][0],
            all_bounds[selected_periods[-1]][1],
        )
        s = datetime.date.fromisoformat(first_ps)
        e = datetime.date.fromisoformat(last_pe)
        period_desc = f"{s.strftime('%b %d')} - {e.strftime('%b %d, %Y')}"
    return _ok(
        {
            "budget": budget["name"],
            "period": period_desc,
            "items": results,
        }
    )


def main():
    """Entry point for the gnucash-mcp CLI."""
    import os

    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        host = os.getenv("MCP_HOST", "127.0.0.1")
        port = int(os.getenv("MCP_PORT", "8990"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

# Implementation Plan — GnuCash MCP Tools

## Current Tool Inventory (10 tools)

| # | Tool | Type | Description |
|---|------|------|-------------|
| 1 | `get_account_balance` | Read | Balance of one account (+ descendants), optional as_of_date |
| 2 | `get_spending_by_category` | Read | Expense totals by account, date range |
| 3 | `get_income_by_category` | Read | Income totals by account, date range |
| 4 | `get_net_worth` | Read | Assets − Liabilities, optional as_of_date |
| 5 | `get_recent_transactions` | Read | Last N transactions for an account |
| 6 | `search_transactions` | Read | Keyword search in descriptions/memos |
| 7 | `list_accounts` | Read | All non-hidden accounts, optional type filter |
| 8 | `get_all_transactions_range` | Read | Earliest/latest transaction dates (NEW) |
| 9 | `get_transaction_count_by_year` | Read | Distinct txn counts per calendar year (NEW) |

## Database Schema Summary

- **22 tables**: accounts, transactions, splits, budgets, budget_amounts, commodities, prices, schedxactions, recurrences, entries, slots, lots, vendors, customers, employees, books, versions, gnclock, billterms, invoices, orders, taxtable_entries, taxtables
- **Budget data**: 2 budgets (Yearly + 2024), 12 periods each. Periods map to monthly windows via recurrences table.
- **Scheduled transactions**: 1 enabled (Mortgage payment). Uses schedxactions + recurrences tables.
- **Prices table**: Empty — no FX rates on file.

---

## Completed

### ✅ Tool 1: `get_all_transactions_range`
**Status:** DONE — 3 tests, live OK
**Result:** 2020-03-10 → 2025-03-04 (~5 years)

### ✅ Tool 2: `get_transaction_count_by_year`
**Status:** DONE — 4 tests, live OK
**Result:** 6 years (2020–2025), massive 2023 spike (547 txns)

### ✅ Tools 3a-b: Date-filtered transaction tools
**Status:** DONE — 6 new tests, live OK
- `get_recent_transactions`: added `start_date`, `end_date`, `order_direction`
- `search_transactions`: same params added

### ✅ Tool 4: Account type filter on `list_accounts`
**Status:** DONE — 3 new tests, live OK

---

## Tool Improvement Ideas (from agent experience)

### 💡 1: `get_spending_by_category` — relative paths + account_type filter
**Motivation:** Agent had to run raw SQL and build recursive CTEs just to get `Expenses:Auto:Fuel` instead of `Fuel`. Also needed EXPENSE-only filtering which the tool doesn't support.
**Design:**
- Add `account_type: str | None = None` — filter by account type (default "EXPENSE", validated against whitelist)
- Add `include_root: bool = False` — if True, return full path from Expenses root (e.g. `Expenses:Auto:Fuel`); if False, return relative path only (e.g. `Auto:Fuel`)
- Uses recursive CTE to build paths from Expenses ROOT account
- Backward compatible: default behavior unchanged (leaf name only)

### 💡 2: ✅ `get_transaction_count_by_year` — date range + account_type filter
**Status:** DONE — 4 new tests, live OK (EXPENSE-only 2023 = 332 txns; Sep–Dec 2023 = 291)
**Design:**
- Add `account_type: str | None` — filter by type (validated against whitelist)
- Add `start_date`, `end_date` — narrow the date range
- Backward compatible: no params = original all-years behavior

### 💡 3: `list_accounts` returning full paths
**Motivation:** Hierarchical path (`Expenses:Auto:Fuel`) requires recursive CTE logic. Current tool returns flat names with pagination.
**Design:**
- Add `full_path: bool = False` — if True, include `path` field built via recursive CTE from ROOT ancestors
- Or separate `get_account_path(guid)` tool for single-account lookup

### 💡 4: `get_spending_by_category` accepting `account_type` filter
**Motivation:** Agent had to manually join and filter for EXPENSE accounts in raw SQL. Existing tool hardcodes "EXPENSE" with no way to switch.
**Design:**
- Add `account_type: str | None = None` — default "EXPENSE", validated against whitelist
- If None, returns all account types (useful for income+expense combined views)

---

## Planned Features (ranked by insight gain)

### 🔥 Priority 1: Budget variance report (`get_budget_variance`)
**Insight gain:** HIGH — turns raw spending into actionable feedback. Compares actuals vs planned amounts with ⚠ markers for over-budget categories.

**Design:**
- `budget_name`: which budget to use (required)
- `period`: which period(s) to report — None (current), int 0–11, "q1"–"q4", "ytd", or "all" (default: current period)
- `account`: optional filter to one account or parent
- Returns per-account breakdown: budgeted, actual, remaining, percent_used

**SQL approach:**
1. Resolve budget → recurrences table for period date bounds
2. Sum budget_amounts for selected periods per account
3. Sum spending_by_category (EXPENSE splits) within same date range
4. Compute variance = budgeted − actual, percent_used = actual/budgeted × 100
5. Compact text table with ⚠ marker at >110%

**Edge cases:**
- Budgets may have incomplete periods (not all accounts in all periods) → only show accounts that have a budget for the selected period(s)
- No FX rates on file → no multi-currency concern currently
- Accounts can appear multiple times per period (TM has 2 entries) → SUM them

**Live data:** 2024 Budget has ~18 expense accounts across 12 periods. Yearly Budget has 4 accounts (Property, Repair/Maintenance, Auto Insurance, Home Insurance).

---

### 🔥 Priority 2: Upcoming scheduled transactions (`get_upcoming_transactions`)
**Insight gain:** HIGH — "what bills are coming up?" query for cash flow planning.

**Design:**
- `days`: look-ahead window (default 14)
- `verbose`: compact text vs JSON (default compact)
- Resolves schedxactions + recurrences tables
- Computes next occurrence date from last_occur + recurrence rules
- Shows: schedule name, next date, amount(s), accounts involved

**SQL approach:**
1. Query schedxactions WHERE enabled = 1
2. Join recurrences for frequency info
3. Calculate next occurrence: last_occur + N × recurrence_mult × period
4. Filter to within `days` window or overdue (past due but not yet entered)

---

### 🔥 Priority 3: Income statement (`get_income_statement`)
**Insight gain:** MEDIUM — consolidated view of revenue minus expenses over a period.

**Design:**
- `start_date`, `end_date`: inclusive range (required)
- Returns: total income, total expenses, net (income − expenses)
- Breakdown by category for both sides

**SQL approach:** Combine get_spending_by_category and get_income_by_category into one call with subtotals.

---

### 🔥 Priority 4: Balance sheet (`get_balance_sheet`)
**Insight gain:** MEDIUM — snapshot of net worth with per-account detail.

**Design:**
- `as_of_date`: optional (default today)
- Returns: assets, liabilities, equity, net_worth
- Per-account breakdown sorted by type then name

---

### 🔥 Priority 5: Monthly spending trend (`get_monthly_spending_trend`)
**Insight gain:** MEDIUM — time-series of total monthly spending.

**Design:**
- `months`: number of months to look back (default 12)
- Returns: array of {month, total_spent} ordered newest first

---

## Implementation Order

1. ~~Tool 1: `get_all_transactions_range`~~ — **DONE** (3 tests, live OK)
2. ~~Tool 2: `get_transaction_count_by_year`~~ — **DONE** (4 tests, live OK)
3. ~~Tools 3a-b: Date-filtered transaction tools~~ — **DONE** (6 new tests, live OK)
4. ~~Tool 4: Account type filter on `list_accounts`~~ — **DONE** (3 new tests, live OK)
5. **Tool 5: `get_budget_variance`** — 🔥 NEXT (highest insight gain)
6. Tool 6: `get_upcoming_transactions`
7. Tool 7: `get_income_statement`
8. Tool 8: `get_balance_sheet`
9. Tool 9: `get_monthly_spending_trend`

---

## Live Results

| Tool | Result |
|------|--------|
| `get_all_transactions_range` | 2020-03-10 → 2025-03-04 |
| `get_transaction_count_by_year` | 6 years, 2023 spike (547 txns) |
| `list_accounts(account_type="EXPENSE")` | 70 expense accounts |
| `list_accounts(account_type="FAKE")` | Proper error with valid types listed |
| `get_recent_transactions("Checking", start_date=..., end_date=...)` | Date-filtered, respects order_direction |
| `search_transactions("transfer", start_date=..., end_date=...)` | 2 matches in H1 2024 |

---

## Testing Strategy

- Each new tool tested via smoke_test.py or direct import
- Modified tools tested for backward compatibility (call without new params)
- Unit tests in `tests/test_server.py` updated
- All 118 tests pass before each commit

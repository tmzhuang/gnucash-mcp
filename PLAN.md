# Implementation Plan — GnuCash MCP Tool Additions

## Overview

Five new tools to improve transaction discovery and date-range querying.

---

## Tool 1: `get_all_transactions_range` (NEW)

**Purpose:** Return the earliest and latest transaction dates across the entire book. One call, done.

**SQL:**
```sql
SELECT MIN(tx.post_date) AS earliest,
       MAX(tx.post_date) AS latest
FROM transactions tx
WHERE EXISTS (
    SELECT 1 FROM splits s WHERE s.tx_guid = tx.guid
)
```

**Implementation:** Append to `server.py` after `_date_bounds_inclusive`. Slice `post_date` to `[:10]` for ISO date strings. No parameters.

**Live result:** `earliest: 2020-03-10`, `latest: 2025-03-04` (~5 years). Earlier than expense-only queries suggested because pre-2016 transactions exist in asset/equity accounts (opening balances, transfers) that pure expense/income tools can't surface.

---

## Tool 2: `get_transaction_count_by_year` (NEW)

**Purpose:** Return transaction counts per calendar year.

**SQL:**
```sql
SELECT YEAR(tx.post_date) AS year,
       COUNT(DISTINCT tx.guid) AS txn_count
FROM transactions tx
WHERE EXISTS (SELECT 1 FROM splits s WHERE s.tx_guid = tx.guid)
GROUP BY YEAR(tx.post_date)
ORDER BY year
```

**Implementation:** Append to `server.py`. Convert year to int for cleaner JSON. No parameters.

**Live result:** 2020–2025, with a massive spike in 2023 (547 txns vs ~25/year otherwise). Likely a bulk import or migration event.

---

## Tool 3: Date-filtered `get_recent_transactions` and `search_transactions`

Both tools lack date filtering. Add optional `start_date`, `end_date` params using `_date_bounds_inclusive`. Default to full range when omitted. Also add optional `order_direction` param (`ASC`/`DESC`).

### 3a. Modified `get_recent_transactions`
- Signature: add `start_date`, `end_date`, `order_direction` (default `"DESC"`)
- SQL: conditional `AND tx.post_date >= %s AND tx.post_date < %s` clause
- Order: use dynamic `ORDER BY tx.post_date {direction}`

### 3b. Modified `search_transactions`
- Signature: same params as above
- SQL: same conditional date clause inserted before the LIMIT

---

## Tool 4: `list_accounts` with optional `account_type` filter

- Signature: add `account_type: str | None = None`
- Validation: reject invalid types, list valid ones in error message
- SQL: conditional `AND a.account_type = %s` clause

---

## Implementation Order

1. ~~Tool 1: `get_all_transactions_range`~~ — **DONE** (3 tests, live OK)
2. ~~Tool 2: `get_transaction_count_by_year`~~ — **DONE** (4 tests, live OK)
3. ~~Tool 3a-b: Date-filtered transaction tools~~ — **DONE** (6 new tests, live OK)
   - `get_recent_transactions`: added `start_date`, `end_date`, `order_direction`
   - `search_transactions`: same params added
4. ~~Tool 4: Account type filter on `list_accounts`~~ — **DONE** (3 new tests, live OK)

## Summary of All Changes

| File | Changes |
|------|---------|
| `server.py` | +2 new tools, modified 3 existing tools with new optional params |
| `tests/test_server.py` | +10 new tests (61→71 server tests), all 118 total pass |
| `smoke_test.py` | Added calls to both new tools |

## Live Results

| Tool | Result |
|------|--------|
| `get_all_transactions_range` | 2020-03-10 → 2025-03-04 |
| `get_transaction_count_by_year` | 6 years, 2023 spike (547 txns) |
| `list_accounts(account_type="EXPENSE")` | 70 expense accounts |
| `list_accounts(account_type="FAKE")` | Proper error with valid types listed |
| `get_recent_transactions("Checking", start_date=..., end_date=...)` | Date-filtered, respects order_direction |
| `search_transactions("transfer", start_date=..., end_date=...)` | 2 matches in H1 2024 |

## Testing Strategy

- Each new tool tested via smoke_test.py or direct import
- Modified tools tested for backward compatibility (call without new params)
- Unit tests in `tests/test_server.py` updated

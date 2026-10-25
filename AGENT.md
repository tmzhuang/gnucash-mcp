# AGENT.md - Development Guidelines

## Project Overview

This project provides a read-only Model Context Protocol (MCP) server that exposes a GnuCash MariaDB database to LLMs. It enables LLMs to answer personal finance questions by executing safe, read-only SQL queries via MCP tools.

**Primary Goal:** Enable natural language querying of personal finance data without risking data mutation.

## Tech Stack & Architecture

*   **Language:** Python 3.10+
*   **Database:** MariaDB (Raw SQL, parameterized queries)
*   **Protocol:** Official MCP Python SDK (stdio transport)
*   **Testing:** `pytest` (unit tests) and standalone smoke tests
*   **Linting:** `ruff`

### File Structure

```
gnucash-mcp/
├── server.py      # MCP server with @mcp.tool() decorators
├── db.py          # Database connection, session constraints, serialization
├── guard.py       # SQL validation and injection prevention
├── smoke_test.py  # Standalone SQL testing without MCP client
├── requirements.txt
├── pyproject.toml
└── docs/          # Architecture and evaluation documentation
```

## Security Constraints

This server implements defense-in-depth to prevent any write operations:

1.  **Database Level:** MariaDB user restricted to `GRANT SELECT` on the schema
2.  **Session Level:** `SET SESSION TRANSACTION READ ONLY` before each query
3.  **Application Level:** `guard.py` validates all SQL (blocks non-SELECT statements)

### Key Security Rules

- ✅ All queries must pass through `guard.check()` before execution
- ✅ Money calculations must use `AMOUNT_EXPR` (DECIMAL, not float)
- ✅ All database exceptions must be caught and returned via JSON envelope
- ✅ Account searches must handle ambiguity with full path resolution

## GnuCash Domain Knowledge

### Double-Entry Accounting
GnuCash stores liabilities and income as negative numbers:
- **Inspection tools:** Return raw ledger values (may be negative)
- **Reporting tools:** Use SQL `ABS()` and rename keys for human readability

### Date Handling
- Accept ISO dates (`YYYY-MM-DD`) from users
- Convert to MariaDB `DATETIME` bounds in Python code

### Account Resolution
- Accept colon-separated paths (e.g., `Assets:Current:EQ Bank`)
- Fall back to substring search if exact match fails
- Return error with candidates if multiple matches exist

## Coding Standards

### Docstrings
Every tool must have an explicit docstring containing:
1. Tool purpose
2. Required arguments with types
3. JSON return format with example

### SQL Formatting
- Keep SQL readable with proper indentation
- Use `AMOUNT_EXPR` for all money-related calculations
- Prefer parameterized queries over string concatenation

### Error Handling
- Catch all database exceptions
- Return graceful errors: `{"ok": false, "error": "message"}`
- Never crash the server

## Testing Protocol

Before committing changes:

1.  **Linting:** `ruff check .`
2.  **Unit Tests:** `pytest tests/`
3.  **Smoke Test:** `python smoke_test.py "account_name"`

## Best Practices

- Keep the flat directory structure
- Mock database functions in unit tests
- Document all tool behaviors in docstrings
- Test edge cases (empty results, ambiguous accounts, date boundaries)

## Evaluation

See `evals/promptfooconfig.yaml` for LLM testing configurations and `docs/evaluation-results.md` for benchmark results.

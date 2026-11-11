"""
SQL guard — defense-in-depth layer for a read-only reporting server.

The MariaDB user already has SELECT-only privileges, so a write cannot
succeed even if this guard is bypassed. The guard exists to:
  * reject accidental multi-statement strings,
  * reject a SELECT that would write files (INTO OUTFILE / INTO DUMPFILE),
  * reject locking clauses (FOR UPDATE / LOCK IN SHARE MODE),
  * make the intent of the server explicit and unit-testable.

Only SELECT and WITH ... SELECT are permitted.
"""

import re

_LEADING = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

_FORBIDDEN = re.compile(
    r"\b("
    r"insert|update|delete|drop|alter|create|truncate|rename|"
    r"grant|revoke|load|call|execute|prepare|deallocate|"
    r"lock|unlock|merge|replace|"
    r"set|use|handler|flush|kill|reset|shutdown|"
    r"into\s+(out|dump)file|"
    r"for\s+update|"
    r"lock\s+in\s+share\s+mode"
    r")\b",
    re.IGNORECASE,
)


def _strip_comments(sql: str) -> str:
    # Block comments first (they may contain '--'), then line comments.
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"#[^\n]*", " ", sql)
    return sql


def check(sql: str) -> str:
    """Validate `sql` is a single read-only statement. Returns `sql` unchanged."""
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("Empty SQL")

    cleaned = _strip_comments(sql).strip()

    # Allow at most one trailing semicolon; anything else is multiple statements.
    body = cleaned.rstrip(";").strip()
    if ";" in body:
        raise ValueError("Multiple SQL statements are not allowed")

    if not _LEADING.match(body):
        raise ValueError("Only SELECT or WITH ... SELECT queries are allowed")

    m = _FORBIDDEN.search(body)
    if m:
        raise ValueError(f"Forbidden keyword in query: {m.group(0)!r}")

    return sql

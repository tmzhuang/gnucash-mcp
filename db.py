"""
MariaDB access layer for the GnuCash read-only MCP server.

Conventions baked into this module (so tools don't repeat them):
  * splits is always aliased as `s`; use AMOUNT_EXPR for money.
  * GnuCash timestamps are CHAR(14) 'YYYYMMDDHHMMSS' — use the helpers below.
  * Every session is forced READ ONLY with a statement timeout before any query.
"""

import datetime
import os
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import mariadb
from dotenv import load_dotenv

import guard

# Load .env from the directory this file lives in — not from cwd, because
# Claude Desktop may launch the process with an arbitrary working directory.
load_dotenv(Path(__file__).resolve().parent / ".env")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "gnucash_ro"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "gnucash"),
}

STATEMENT_TIMEOUT_S = float(os.getenv("QUERY_TIMEOUT_S", "10"))

# GnuCash stores money as (value_num, value_denom) integer pairs. Never
# treat value_num as a float. This expression is safe against denom = 0.
# Assumes splits is aliased as `s` in the enclosing query.
AMOUNT_EXPR = "CAST(s.value_num AS DECIMAL(20,6)) / NULLIF(s.value_denom, 0)"

# GnuCash stores timestamps as DATETIME.
# SQL side:  post_date is DATETIME column.
# Python side:
def parse_gnucash_date(s: str) -> datetime.datetime:
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def format_gnucash_date(d: datetime.datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S")


def _jsonable(v: Any) -> Any:
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    return v  # Decimal, int, str, None pass through unchanged



@contextmanager
def _connection():
    conn = mariadb.connect(**DB_CONFIG, autocommit=True)
    try:
        cur = conn.cursor()
        try:
            # Layer 2: force the session into READ ONLY mode.
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            # Layer 3: cap runtime. Cast to float before interpolation so a
            # malicious .env cannot inject anything.
            cur.execute(f"SET SESSION max_statement_time = {float(STATEMENT_TIMEOUT_S)}")
        finally:
            cur.close()
        yield conn
    finally:
        conn.close()


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run a validated read-only query and return JSON-serializable rows."""
    guard.check(sql)
    with _connection() as conn:
        cur = conn.cursor(dictionary=True)
        try:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            rows = cur.fetchall()
        finally:
            cur.close()
    return [{k: _jsonable(v) for k, v in row.items()} for row in rows]

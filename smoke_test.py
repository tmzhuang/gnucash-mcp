"""
Exercise each MCP tool directly in Python — no MCP client required.

Run:  python smoke_test.py
      python smoke_test.py Checking   # override the account substring
"""

import json
import sys

import server


def _show(label: str, raw: str) -> None:
    print(f"\n=== {label} ===")
    try:
        print(json.dumps(json.loads(raw), indent=2))
    except json.JSONDecodeError:
        print(raw)


def main() -> int:
    account = sys.argv[1] if len(sys.argv) > 1 else "Checking"

    _show("list_accounts", server.list_accounts())
    _show(f"get_account_balance({account!r})", server.get_account_balance(account))
    _show(
        f"get_recent_transactions({account!r}, limit=5)",
        server.get_recent_transactions(account, limit=5),
    )
    _show(
        "get_spending_by_category(2024-08-01 .. 2024-10-31)",
        server.get_spending_by_category("2024-08-01", "2024-10-31"),
    )
    _show(
        "search_transactions('grocery', limit=5)",
        server.search_transactions("grocery", limit=5),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

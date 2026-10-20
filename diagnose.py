"""Standalone diagnostic — check what's actually in splits for EQ Bank."""
import json
from db import query

# GUID of EQ Bank from your earlier list_accounts output
EQ_BANK_GUID = "a3b003626e4348d4a3fa0bbcf2f1cc85"


def main():
    print("=== 1. Splits summary for EQ Bank + all descendants ===")
    rows = query(
        """
        WITH RECURSIVE tree AS (
            SELECT guid FROM accounts WHERE guid = %s
            UNION ALL
            SELECT a.guid FROM accounts a JOIN tree t ON a.parent_guid = t.guid
        )
        SELECT COUNT(*)           AS n_splits,
               SUM(s.value_num)   AS sum_value_num,
               SUM(s.value_denom) AS sum_value_denom,
               SUM(s.quantity_num)   AS sum_quantity_num,
               SUM(s.quantity_denom) AS sum_quantity_denom,
               MIN(tx.post_date)  AS first_date,
               MAX(tx.post_date)  AS last_date
        FROM splits s
        JOIN transactions tx ON tx.guid = s.tx_guid
        WHERE s.account_guid IN (SELECT guid FROM tree)
        """,
        (EQ_BANK_GUID,),
    )
    print(json.dumps(rows, indent=2, default=str))

    print("\n=== 2. Are there splits on EQ Bank directly (no children)? ===")
    rows = query(
        """
        SELECT COUNT(*) AS n_splits,
               SUM(s.value_num) AS sum_value_num,
               SUM(s.value_denom) AS sum_value_denom,
               MIN(tx.post_date) AS first_date,
               MAX(tx.post_date) AS last_date
        FROM splits s
        JOIN transactions tx ON tx.guid = s.tx_guid
        WHERE s.account_guid = %s
        """,
        (EQ_BANK_GUID,),
    )
    print(json.dumps(rows, indent=2, default=str))

    print("\n=== 3. Latest 5 splits (any account) — sanity check the book has data ===")
    rows = query(
        """
        SELECT tx.post_date, tx.description, a.name AS account,
               s.value_num, s.value_denom, s.quantity_num, s.quantity_denom
        FROM splits s
        JOIN transactions tx ON tx.guid = s.tx_guid
        JOIN accounts a ON a.guid = s.account_guid
        ORDER BY tx.post_date DESC
        LIMIT 5
        """
    )
    print(json.dumps(rows, indent=2, default=str))


if __name__ == "__main__":
    main()

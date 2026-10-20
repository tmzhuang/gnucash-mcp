"""Prove exactly where the zero balance comes from."""
from decimal import Decimal
from db import query

EQ_BANK_GUID = "a3b003626e4348d4a3fa0bbcf2f1cc85"

TREE = """
WITH RECURSIVE tree AS (
    SELECT guid FROM accounts WHERE guid = %s
    UNION ALL
    SELECT a.guid FROM accounts a JOIN tree t ON a.parent_guid = t.guid
)
"""


def q(sql, params=()):
    return query(sql, params)


print("=== A. Exact tool query (with date filter) ===")
print(q(
    TREE + """
    SELECT COALESCE(SUM(CAST(s.value_num AS DECIMAL(20,6)) / NULLIF(s.value_denom, 0)), 0)
           AS balance
    FROM splits s
    JOIN transactions tx ON tx.guid = s.tx_guid
    WHERE s.account_guid IN (SELECT guid FROM tree)
      AND tx.post_date < %s
    """,
    (EQ_BANK_GUID, "99999999999999"),
))

print("\n=== B. Same query WITHOUT date filter ===")
print(q(
    TREE + """
    SELECT COALESCE(SUM(CAST(s.value_num AS DECIMAL(20,6)) / NULLIF(s.value_denom, 0)), 0)
           AS balance
    FROM splits s
    WHERE s.account_guid IN (SELECT guid FROM tree)
    """,
    (EQ_BANK_GUID,),
))

print("\n=== C. Per-split detail ===")
rows = q(
    TREE + """
    SELECT a.name AS account, tx.post_date, tx.description,
           s.value_num, s.value_denom,
           s.quantity_num, s.quantity_denom
    FROM splits s
    JOIN transactions tx ON tx.guid = s.tx_guid
    JOIN accounts a ON a.guid = s.account_guid
    WHERE s.account_guid IN (SELECT guid FROM tree)
    ORDER BY tx.post_date
    """,
    (EQ_BANK_GUID,),
)
for r in rows:
    print(r)

print("\n=== D. Sum in Python with Decimal (ground truth) ===")
total = Decimal(0)
for r in rows:
    vn, vd = r["value_num"], r["value_denom"]
    if vd:
        total += Decimal(vn) / Decimal(vd)
print(f"Decimal sum: {total}")

print("\n=== E. Raw sums as reported before ===")
print(q(
    TREE + """
    SELECT COUNT(*) AS n,
           SUM(s.value_num) AS sum_value_num,
           SUM(s.value_denom) AS sum_value_denom,
           SUM(s.quantity_num) AS sum_quantity_num,
           SUM(s.quantity_denom) AS sum_quantity_denom
    FROM splits s
    WHERE s.account_guid IN (SELECT guid FROM tree)
    """,
    (EQ_BANK_GUID,),
))

"""Tests for guard.py - SQL validation layer."""

import pytest

from guard import _strip_comments, check


class TestStripComments:
    """Test comment removal."""

    def test_block_comment_removed(self):
        sql = "SELECT 1 /* this is a comment */ 2"
        assert _strip_comments(sql) == "SELECT 1   2"

    def test_line_comment_removed(self):
        sql = "SELECT 1 -- this is a comment\n2"
        # Line comment replaced with space(s)
        assert "--" not in _strip_comments(sql)

    def test_hash_comment_removed(self):
        sql = "SELECT 1 --# this is a comment\n2"
        # Hash comment replaced with space(s)
        assert "#" not in _strip_comments(sql)

    def test_multiple_comments(self):
        sql = """
        SELECT /* block */ 1
        -- line comment
        FROM table
        # hash comment
        """
        cleaned = _strip_comments(sql)
        assert "/*" not in cleaned
        assert "--" not in cleaned
        assert "#" not in cleaned

    def test_no_comments_unchanged(self):
        sql = "SELECT 1 FROM table WHERE x = 2"
        assert _strip_comments(sql) == sql


class TestCheck:
    """Test SQL validation."""

    def test_valid_select(self):
        assert check("SELECT 1") == "SELECT 1"

    def test_valid_select_with_where(self):
        sql = "SELECT * FROM accounts WHERE hidden = 0"
        assert check(sql) == sql

    def test_valid_with_cte(self):
        sql = """
        WITH RECURSIVE tree AS (
            SELECT guid FROM accounts WHERE guid = %s
            UNION ALL
            SELECT a.guid FROM accounts a JOIN tree t ON a.parent_guid = t.guid
        )
        SELECT guid FROM tree
        """
        assert check(sql) == sql

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Empty SQL"):
            check("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="Empty SQL"):
            check("   ")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="Empty SQL"):
            check(123)

    def test_multiple_statements_raises(self):
        with pytest.raises(ValueError, match="Multiple SQL statements"):
            check("SELECT 1; SELECT 2")

    def test_trailing_semicolon_allowed(self):
        assert check("SELECT 1;") == "SELECT 1;"

    def test_multiple_statements_in_middle_raises(self):
        with pytest.raises(ValueError, match="Multiple SQL statements"):
            check("SELECT 1; 2")

    def test_insert_forbidden(self):
        with pytest.raises(ValueError, match="Only SELECT or WITH"):
            check("INSERT INTO accounts SELECT 1")

    def test_update_forbidden(self):
        with pytest.raises(ValueError, match="Only SELECT or WITH"):
            check("UPDATE accounts SET x = 1")

    def test_delete_forbidden(self):
        with pytest.raises(ValueError, match="Only SELECT or WITH"):
            check("DELETE FROM accounts")

    def test_create_forbidden(self):
        with pytest.raises(ValueError, match="Only SELECT or WITH"):
            check("CREATE TABLE test (x INT)")

    def test_drop_forbidden(self):
        with pytest.raises(ValueError, match="Only SELECT or WITH"):
            check("DROP TABLE accounts")

    def test_set_forbidden(self):
        with pytest.raises(ValueError, match="Only SELECT or WITH"):
            check("SET SESSION x = 1")

    def test_into_outfile_forbidden(self):
        with pytest.raises(ValueError, match="Forbidden keyword"):
            check("SELECT 1 INTO OUTFILE '/tmp/x'")

    def test_into_dumpfile_forbidden(self):
        with pytest.raises(ValueError, match="Forbidden keyword"):
            check("SELECT 1 INTO DUMPFILE '/tmp/x'")

    def test_for_update_forbidden(self):
        with pytest.raises(ValueError, match="Forbidden keyword"):
            check("SELECT * FROM accounts FOR UPDATE")

    def test_lock_in_share_mode_forbidden(self):
        with pytest.raises(ValueError, match="Forbidden keyword"):
            check("SELECT * FROM accounts LOCK IN SHARE MODE")

    def test_case_insensitive_forbidden_keyword(self):
        # UPDATE is case insensitive and forbidden
        with pytest.raises(ValueError, match="Only SELECT or WITH"):
            check("update accounts SET x = 1")

    def test_valid_case_insensitive_select(self):
        assert check("select * from accounts") == "select * from accounts"

    def test_valid_uppercase_select(self):
        assert check("SELECT * FROM accounts") == "SELECT * FROM accounts"

    def test_valid_with_camelcase_keyword_allowed(self):
        # SELECT is allowed even in camelCase-like strings
        assert check("SELECT x FROM y WHERE z = 1") == "SELECT x FROM y WHERE z = 1"

    def test_invalid_starting_with_dml(self):
        with pytest.raises(ValueError, match="Only SELECT or WITH"):
            check("INSERT INTO x SELECT 1")

    def test_invalid_starting_with_update(self):
        with pytest.raises(ValueError, match="Only SELECT or WITH"):
            check("UPDATE x SET y = 1")

    def test_valid_with_cte_and_subquery(self):
        sql = """
        WITH RECURSIVE cte AS (
            SELECT 1 AS x
            UNION ALL
            SELECT x + 1 FROM cte WHERE x < 10
        )
        SELECT * FROM cte
        """
        assert check(sql) == sql

    def test_valid_complex_select(self):
        sql = """
        SELECT a.name, SUM(s.value_num) / NULLIF(s.value_denom, 0) AS total
        FROM splits s
        JOIN accounts a ON a.guid = s.account_guid
        WHERE a.hidden = 0
        GROUP BY a.name
        HAVING total > 0
        ORDER BY total DESC
        """
        assert check(sql) == sql

    def test_valid_with_order_by_and_limit(self):
        sql = "SELECT * FROM accounts ORDER BY name LIMIT 100"
        assert check(sql) == sql

    def test_valid_with_join(self):
        sql = (
            "SELECT a.*, b.* FROM accounts a JOIN transactions b ON a.id = b.account_id"
        )
        assert check(sql) == sql

    def test_valid_with_union(self):
        sql = "SELECT 1 FROM a UNION SELECT 2 FROM b"
        assert check(sql) == sql

    def test_valid_with_union_all(self):
        sql = "SELECT 1 FROM a UNION ALL SELECT 2 FROM b"
        assert check(sql) == sql

    def test_valid_with_case_expression(self):
        sql = "SELECT CASE WHEN x > 0 THEN 'positive' ELSE 'negative' END FROM accounts"
        assert check(sql) == sql

    def test_valid_with_cast(self):
        sql = "SELECT CAST(x AS DECIMAL(10,2)) FROM accounts"
        assert check(sql) == sql

    def test_valid_with_function_call(self):
        sql = "SELECT DATE(post_date), SUM(amount) FROM transactions GROUP BY DATE(post_date)"
        assert check(sql) == sql

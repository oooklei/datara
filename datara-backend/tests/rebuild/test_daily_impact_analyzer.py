from rebuild.impact import analyze_history_entry


def history(sql: str, success: bool = True):
    return {"id": "h1", "connection_id": "conn-1", "database": "sales", "executed_at": "2026-10-29T10:00:00", "sql": sql, "success": success}


def test_insert_select_captures_read_to_write_effect():
    result = analyze_history_entry(history("INSERT INTO report SELECT * FROM orders"))
    assert result["reads"] == ["sales.orders"]
    assert result["writes"] == ["sales.report"]
    assert "sql" not in result


def test_create_table_as_select_captures_new_object():
    result = analyze_history_entry(history("CREATE TABLE summary AS SELECT * FROM orders"))
    assert result["reads"] == ["sales.orders"]
    assert result["writes"] == ["sales.summary"]


def test_cte_name_is_not_reported_as_physical_table():
    result = analyze_history_entry(history("WITH recent AS (SELECT * FROM orders) INSERT INTO report SELECT * FROM recent"))
    assert result["reads"] == ["sales.orders"]
    assert result["writes"] == ["sales.report"]


def test_failed_execution_does_not_claim_write_effect():
    result = analyze_history_entry(history("DELETE FROM orders", success=False))
    assert result["status"] == "failed_execution"
    assert result["writes"] == []


def test_unparseable_statement_is_marked_unknown():
    result = analyze_history_entry(history("SELECT FROM"))
    assert result["status"] == "unparsed"
    assert result["reads"] == []

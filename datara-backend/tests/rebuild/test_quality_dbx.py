import pytest

from rebuild.governance.quality_dbx import (
    QualityPredicateError, compile_quality_count_query, parse_quality_counts,
)


def test_compiles_real_customer_format_rule_into_read_only_count():
    sql = compile_quality_count_query(
        database="ec_retail", table="dim_user", fields={"id_card", "phone"},
        expression='LENGTH(TRIM(id_card)) = 18 AND id_card REGEXP "^[0-9Xx]{18}$"',
    )
    assert "FROM `ec_retail`.`dim_user`" in sql
    assert "COUNT(*) AS checked_rows" in sql
    assert "REGEXP" in sql
    assert "THEN 0 ELSE 1" in sql


@pytest.mark.parametrize("expression", [
    "id_card IS NOT NULL; DELETE FROM dim_user",
    "EXISTS (SELECT 1 FROM secret_table)",
    "other_field IS NOT NULL",
    "db.dim_user.id_card IS NOT NULL",
    "LOAD_FILE('/etc/passwd') IS NOT NULL",
    "1 = 1",
])
def test_rejects_unsafe_or_out_of_asset_predicates(expression):
    with pytest.raises(QualityPredicateError):
        compile_quality_count_query(
            database="ec_retail", table="dim_user", fields={"id_card"}, expression=expression,
        )


def test_parses_dbx_string_counts_and_rejects_truncated_response():
    response = {"columns": ["checked_rows", "failed_rows"], "rows": [["60002", "2"]], "truncated": False}
    assert parse_quality_counts(response) == (60002, 2)
    with pytest.raises(QualityPredicateError):
        parse_quality_counts({**response, "truncated": True})

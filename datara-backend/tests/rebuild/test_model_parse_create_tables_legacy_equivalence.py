"""17.2-20 A6-20 `parse_create_tables` 差分等价测试（旧侧 vs rebuild 侧）。

- 旧侧实锚 `datara-backend/common/sqlparser.py:289-337`（`parse_create_tables`）。
- rebuild 落点 `rebuild/model/ddlparser.py`（随票下沉，纯函数）。

对同一段 DDL 文本，断言两侧输出 `[{name, comment, fields[]}]` **全等**；
并覆盖语法错误路径（两侧同抛 `sqlglot.errors.ParseError`）。

纯函数（无 DB / 无网络）→ 差分可脱离数据库运行。
"""

import pytest
import sqlglot

pytest.importorskip("common.sqlparser")

from common.sqlparser import parse_create_tables as legacy_parse
from rebuild.model.ddlparser import parse_create_tables as rebuild_parse

SQL_SAMPLES = {
    "simple": "CREATE TABLE ods_t (id BIGINT NOT NULL, name VARCHAR(64));",
    "table_comment": "CREATE TABLE ods_t (id BIGINT) COMMENT='表注释';",
    "inline_pk": "CREATE TABLE ods_t (id BIGINT NOT NULL PRIMARY KEY, name VARCHAR(64));",
    "table_level_pk": "CREATE TABLE ods_t (a BIGINT, b BIGINT, PRIMARY KEY (a, b));",
    "default_literal": "CREATE TABLE ods_t (id BIGINT DEFAULT 0, name VARCHAR(8) DEFAULT 'x');",
    "default_expression": "CREATE TABLE ods_t (ts DATETIME DEFAULT CURRENT_TIMESTAMP);",
    "column_comment": "CREATE TABLE ods_t (id BIGINT COMMENT '主键', name VARCHAR(8) COMMENT '名称');",
    "decimal_precision_scale": "CREATE TABLE ods_t (amt DECIMAL(12,2), qty DECIMAL(10,0));",
    "nullable_mixed": "CREATE TABLE ods_t (a BIGINT, b BIGINT NULL);",
    "multi_tables": "CREATE TABLE ods_a (id BIGINT); CREATE TABLE ods_b (id BIGINT);",
    "non_create_ignored": "INSERT INTO ods_t VALUES (1); SELECT * FROM ods_t;",
    "create_view_ignored": "CREATE VIEW v AS SELECT 1;",
    "create_index_ignored": "CREATE TABLE ods_t (id BIGINT); CREATE INDEX idx ON ods_t (id);",
    "qualified_name": "CREATE TABLE mydb.ods_t (id BIGINT);",
    "empty_columns": "CREATE TABLE ods_t ();",
    "unique_key": "CREATE TABLE ods_t (a VARCHAR(8) UNIQUE, b VARCHAR(8) NOT NULL UNIQUE KEY);",
    "auto_increment": "CREATE TABLE ods_t (id BIGINT AUTO_INCREMENT, PRIMARY KEY (id));",
    "enum_set": "CREATE TABLE ods_t (s ENUM('a','b'), t SET('x'));",
    "if_not_exists": "CREATE TABLE IF NOT EXISTS ods_t (id BIGINT);",
    "utf8_comment": "CREATE TABLE ods_t (id BIGINT COMMENT '中文注释');",
    "engine_suffix": "CREATE TABLE ods_t (id BIGINT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
}

NAMES = list(SQL_SAMPLES)


@pytest.mark.parametrize("name", NAMES)
def test_parse_create_tables_matches_legacy(name):
    """两侧对同一段 DDL 输出全等（含字段序与 `fields[]` 每项键值）。"""
    sql = SQL_SAMPLES[name]
    assert rebuild_parse(sql) == legacy_parse(sql)


def test_parse_create_tables_syntax_error_matches_legacy():
    """语法错误：两侧同抛 `sqlglot.errors.ParseError`，且 `line` 属性一致。"""
    bad = "CREATE TABLE ods_t (id BIGINT"
    with pytest.raises(sqlglot.errors.ParseError) as legacy_exc:
        legacy_parse(bad)
    with pytest.raises(sqlglot.errors.ParseError) as rebuild_exc:
        rebuild_parse(bad)
    assert getattr(rebuild_exc.value, "line", None) == getattr(legacy_exc.value, "line", None)


def test_parse_create_tables_empty_and_none_input_match_legacy():
    """空串 / 纯注释 / 纯空白：两侧同为 `[]`。"""
    for sql in ("", "-- just a comment\n", "   \n\t "):
        assert rebuild_parse(sql) == legacy_parse(sql) == []


def test_parse_create_tables_is_pure_and_repeatable():
    """纯函数：同输入两次调用结果一致（无隐藏状态）。"""
    sql = SQL_SAMPLES["table_level_pk"]
    assert rebuild_parse(sql) == rebuild_parse(sql)
    assert legacy_parse(sql) == rebuild_parse(sql)

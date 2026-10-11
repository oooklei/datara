"""ddlgen DDL 三方言生成器单测（快照断言 + 注入拦截 + 分区提示 + 类型白名单/长度校验/转义）。"""

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from common.ddlgen import dialect_notes, gen_ddl  # noqa: E402

FIELDS = [
    {"name": "user_id", "dataType": "BIGINT", "length": "", "precision": "", "nullable": False,
     "defaultValue": "", "comment": "用户ID", "isPk": True, "isPartition": False, "dictRef": ""},
    {"name": "user_name", "dataType": "VARCHAR", "length": "100", "precision": "", "nullable": True,
     "defaultValue": "", "comment": "姓名", "isPk": False, "isPartition": False, "dictRef": ""},
    {"name": "amount", "dataType": "DECIMAL", "length": "18", "precision": "2", "nullable": True,
     "defaultValue": "", "comment": "金额", "isPk": False, "isPartition": False, "dictRef": ""},
    {"name": "dt", "dataType": "DATE", "length": "", "precision": "", "nullable": True,
     "defaultValue": "", "comment": "分区字段", "isPk": False, "isPartition": True, "dictRef": ""},
]


def test_mysql_snapshot():
    sql = gen_ddl("dwd_order_pay", "订单支付明细", FIELDS, "mysql")
    assert sql == (
        "CREATE TABLE `dwd_order_pay` (\n"
        "  `user_id` BIGINT NOT NULL COMMENT '用户ID',\n"
        "  `user_name` VARCHAR(100) COMMENT '姓名',\n"
        "  `amount` DECIMAL(18,2) COMMENT '金额',\n"
        "  `dt` DATE COMMENT '分区字段',\n"
        "  PRIMARY KEY (`user_id`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单支付明细'"
    )


def test_greatdb_same_family_as_mysql():
    assert gen_ddl("t", "t", FIELDS, "greatdb") == gen_ddl("t", "t", FIELDS, "mysql")


def test_doris_partition_and_hash():
    sql = gen_ddl("dwd_order_pay", "订单支付明细", FIELDS, "doris")
    assert "PARTITION BY RANGE(`dt`) ()" in sql
    assert "DISTRIBUTED BY HASH(`user_id`) BUCKETS 10" in sql
    assert "'dynamic_partition.enable' = 'true'" in sql


def test_mysql_partition_note():
    assert dialect_notes(FIELDS, "mysql") == ["该引擎不支持分区声明"]
    assert dialect_notes(FIELDS, "doris") == []


def test_default_value_rendered():
    f = [{"name": "gender", "dataType": "CHAR", "length": "1", "precision": "", "nullable": True,
          "defaultValue": "M", "comment": "性别", "isPk": False, "isPartition": False, "dictRef": ""}]
    assert "DEFAULT 'M'" in gen_ddl("t", "t", f, "mysql")


def test_bad_ident_rejected():
    with pytest.raises(ValueError):
        gen_ddl("bad;drop", "x", FIELDS, "mysql")
    with pytest.raises(ValueError):
        gen_ddl("t", "x", [{"name": "a;b", "dataType": "INT", "length": "", "precision": "",
                            "nullable": True, "defaultValue": "", "comment": "",
                            "isPk": False, "isPartition": False, "dictRef": ""}], "mysql")


def test_comment_quote_escaped():
    f = [{"name": "c", "dataType": "INT", "length": "", "precision": "", "nullable": True,
          "defaultValue": "", "comment": "it's ok", "isPk": False, "isPartition": False, "dictRef": ""}]
    assert "COMMENT 'it''s ok'" in gen_ddl("t", "t", f, "mysql")


def test_type_not_in_whitelist_rejected():
    f = dict(FIELDS[0]); f["dataType"] = "INT) ENGINE=InnoDB; DROP TABLE x--"
    with pytest.raises(ValueError):
        gen_ddl("t", "t", [f], "mysql")


def test_length_precision_injection_rejected():
    f = dict(FIELDS[1]); f["length"] = "100) ENGINE=InnoDB; DROP TABLE x--"
    with pytest.raises(ValueError):
        gen_ddl("t", "t", [f], "mysql")
    f2 = dict(FIELDS[2]); f2["precision"] = "2); DROP TABLE x--"
    with pytest.raises(ValueError):
        gen_ddl("t", "t", [f2], "mysql")
    f3 = dict(FIELDS[2]); f3["length"] = ""
    with pytest.raises(ValueError):
        gen_ddl("t", "t", [f3], "mysql")


def test_empty_fields_rejected():
    with pytest.raises(ValueError):
        gen_ddl("t", "t", [], "mysql")
    with pytest.raises(ValueError):
        gen_ddl("t", "t", FIELDS, "pg")


def test_backslash_escaped_in_literal():
    f = [{"name": "c", "dataType": "INT", "length": "", "precision": "", "nullable": True,
          "defaultValue": "\\", "comment": "x", "isPk": False, "isPartition": False, "dictRef": ""}]
    assert "DEFAULT '\\\\'" in gen_ddl("t", "t", f, "mysql")


# ---------- parse_create_tables（I18 DDL 文件逆向导入） ----------

DDL_SQL = """
CREATE TABLE `ods_gdb_biz_user_info` (
  `user_id` BIGINT NOT NULL COMMENT '用户ID',
  `user_name` VARCHAR(100) DEFAULT 'anon' COMMENT '姓名',
  `amount` DECIMAL(18,2) COMMENT '金额',
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户信息原始表';

INSERT INTO log VALUES (1);
"""


def test_parse_create_tables():
    from common.sqlparser import parse_create_tables

    out = parse_create_tables(DDL_SQL)
    assert len(out) == 1
    t = out[0]
    assert t["name"] == "ods_gdb_biz_user_info"
    assert t["comment"] == "用户信息原始表"
    f = {x["name"]: x for x in t["fields"]}
    assert f["user_id"]["isPk"] is True and f["user_id"]["dataType"] == "BIGINT"
    assert f["user_name"]["dataType"] == "VARCHAR" and f["user_name"]["length"] == "100"
    assert f["user_name"]["defaultValue"] == "anon"
    assert f["user_name"]["nullable"] is True
    assert f["amount"]["length"] == "18" and f["amount"]["precision"] == "2"


def test_parse_create_tables_bad_sql():
    from sqlglot.errors import ParseError

    from common.sqlparser import parse_create_tables

    with pytest.raises(ParseError) as ei:
        parse_create_tables("CREATE TABLE `x` (")
    assert "Line" in str(ei.value)


DDL_SQL_MULTI = """
CREATE TABLE `dwd_t1` (
  `id` BIGINT PRIMARY KEY COMMENT '内联主键',
  `amt` DECIMAL(10,2)
) ENGINE=InnoDB COMMENT='表一';

CREATE TABLE `ods_t2` (
  `code` VARCHAR(32) NOT NULL,
  `name` VARCHAR(100)
);
"""


def test_parse_create_tables_inline_pk_and_multi():
    from common.sqlparser import parse_create_tables

    out = parse_create_tables(DDL_SQL_MULTI)
    assert len(out) == 2
    t1 = next(t for t in out if t["name"] == "dwd_t1")
    assert t1["comment"] == "表一"
    f1 = {x["name"]: x for x in t1["fields"]}
    assert f1["id"]["isPk"] is True and f1["id"]["nullable"] is False
    t2 = next(t for t in out if t["name"] == "ods_t2")
    assert t2["comment"] == ""
    f2 = {x["name"]: x for x in t2["fields"]}
    assert f2["code"]["nullable"] is False and f2["code"]["isPk"] is False
    assert f2["name"]["nullable"] is True

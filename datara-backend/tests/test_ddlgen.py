"""ddlgen DDL 三方言生成器单测（快照断言 + 注入拦截 + 分区提示）。"""

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

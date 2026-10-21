"""17.2-16 差分等价测试：`rebuild/model/ddlgen.py` 移植件 vs 旧侧 `common/ddlgen.py`。

**本文件是迁移保真度的差分锁定件，不是 rebuild 运行时依赖。**
`rebuild/model/ddlgen.py` 是旧侧 `common/ddlgen.py:17-110` + `common/dsconn.py:77-88`
的逐行移植（唯一改动：`quote_ident` 由跨模块 import 改为本模块自带，避开旧
`common/dsconn` 模块级 `import pymysql` + `from common.models import DataSource`
拖入全量旧 ORM 元数据）。

为证明「照抄不重构」不是纸面声明，本文件对同一输入矩阵**同时**调用两侧生成器并逐字比对：
① 成功路径 → DDL 文本 `==` 全等；
② 失败路径 → 两侧 `ValueError` 的 `str()` 全等。

旧侧不可导入时整体 `importorskip` 跳过（第⑤步下线旧侧后本文件应随迁移收尾一并删除）。
"""

import pytest

pytest.importorskip("common.ddlgen", reason="旧侧 common.ddlgen 不在导入路径，跳过差分")

from common.ddlgen import dialect_notes as legacy_notes  # noqa: E402
from common.ddlgen import gen_ddl as legacy_gen_ddl  # noqa: E402
from common.dsconn import quote_ident as legacy_quote_ident  # noqa: E402

from rebuild.model.ddlgen import dialect_notes, gen_ddl, quote_ident  # noqa: E402


def _field(name, data_type="BIGINT", **over):
    base = {"name": name, "dataType": data_type, "length": "", "precision": "",
            "nullable": True, "defaultValue": "", "comment": "",
            "isPk": False, "isPartition": False, "dictRef": ""}
    base.update(over)
    return base


# ---------------------------------------------------------------- 成功路径矩阵

_CASES = [
    # (code, name, fields, engine)
    ("dwd_trade_order", "订单明细", [
        _field("id", data_type="BIGINT", isPk=True, nullable=False),
        _field("amt", data_type="DECIMAL", length="18", precision="2",
               defaultValue="0", comment="金额"),
    ], "mysql"),
    ("dwd_trade_order", "订单明细", [
        _field("id", data_type="BIGINT", isPk=True, nullable=False),
    ], "greatdb"),
    ("ads_trade_sum", "交易汇总", [
        _field("dt", data_type="DATE", isPartition=True),
        _field("id", data_type="BIGINT", isPk=True, nullable=False),
        _field("amt", data_type="DOUBLE", defaultValue="0.00"),
    ], "doris"),
    ("dws_user_1d", "用户日汇总", [
        _field("id", data_type="BIGINT", isPk=True, nullable=False),
        _field("dt", data_type="DATE", isPartition=True),
    ], "doris"),
    ("dwd_raw_log", "原始日志", [
        _field("id", data_type="BIGINT"),
        _field("payload", data_type="TEXT", comment="含'单引号'与\\反斜杠"),
        _field("ratio", data_type="DOUBLE", nullable=False, defaultValue="1"),
        _field("created_at", data_type="DATETIME", comment="创建时间"),
        _field("code", data_type="CHAR", length="8"),
        _field("flag", data_type="TINYINT"),
        _field("amount", data_type="INT"),
    ], "mysql"),
    ("dim_user", "用户维表", [_field("id", data_type="BIGINT", isPk=True)], "doris"),
    ("dwd_empty_pk", "无主键无分区", [_field("a", data_type="VARCHAR", length="16")], "doris"),
    ("dwd_no_pk_mysql", "无主键", [_field("a", data_type="INT")], "mysql"),
    ("ods_src_tbl", "源表", [
        _field("sync_date", data_type="DATE", isPartition=True),
        _field("id", data_type="BIGINT", isPk=True, nullable=False),
        _field("name", data_type="VARCHAR", length="64", comment="名"),
    ], "greatdb"),
]


@pytest.mark.parametrize("code,name,fields,engine", _CASES, ids=[c[3] + ":" + c[0] for c in _CASES])
def test_gen_ddl_matches_legacy_byte_for_byte(code, name, fields, engine):
    """成功路径：移植件与旧侧 DDL 文本**逐字全等**。"""
    assert gen_ddl(code, name, fields, engine) == legacy_gen_ddl(code, name, fields, engine)


@pytest.mark.parametrize("code,name,fields,engine", _CASES, ids=[c[3] + ":" + c[0] for c in _CASES])
def test_dialect_notes_match_legacy(code, name, fields, engine):
    """方言提示：移植件与旧侧列表全等。"""
    assert dialect_notes(fields, engine) == legacy_notes(fields, engine)


def test_quote_ident_matches_legacy():
    """标识符校验：合法名同样反引号包裹，非法名同样 ValueError 且文案一致。"""
    for legal in ["dwd_trade_order", "20260101-9999-i3t_x", "表名"]:
        assert quote_ident(legal) == legacy_quote_ident(legal)
    for illegal in ["", "bad name", "a`b", "a;b", "a'b"]:
        with pytest.raises(ValueError) as new:
            quote_ident(illegal)
        with pytest.raises(ValueError) as old:
            legacy_quote_ident(illegal)
        assert str(new.value) == str(old.value)


# ---------------------------------------------------------------- 失败路径矩阵

_ERROR_CASES = [
    ("dwd_x", "x", [], "mysql"),                                        # 空字段列表
    ("dwd_x", "x", [_field("id")], "oracle"),                           # 不支持的引擎
    ("dwd_x", "x", [_field("a", data_type="FOO")], "mysql"),            # 类型不在白名单
    ("dwd_x", "x", [_field("a", data_type="VARCHAR", length="abc")], "mysql"),
    ("dwd_x", "x", [_field("a", data_type="VARCHAR", length="1234567890")], "mysql"),
    ("dwd_x", "x", [_field("a", data_type="DECIMAL", precision="2")], "mysql"),
    ("dwd_x", "x", [_field("a", data_type="DECIMAL", length="18", precision="x")], "mysql"),
    ("dwd_x", "x", [_field("bad name")], "mysql"),                      # 非法字段标识符
    ("dwd_x", "x", [_field("")], "mysql"),                              # 空字段名
    ("bad code", "x", [_field("id")], "mysql"),                         # 非法表名标识符
]


@pytest.mark.parametrize(
    "code,name,fields,engine", _ERROR_CASES, ids=[f"err{i}" for i in range(len(_ERROR_CASES))]
)
def test_gen_ddl_error_matches_legacy(code, name, fields, engine):
    """失败路径：两侧同样抛 `ValueError` 且 `str()` 文案全等。"""
    with pytest.raises(ValueError) as new:
        gen_ddl(code, name, fields, engine)
    with pytest.raises(ValueError) as old:
        legacy_gen_ddl(code, name, fields, engine)
    assert str(new.value) == str(old.value)

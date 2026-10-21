"""17.2-19 A6-19 `_col_to_field` 差分等价测试（旧侧 vs rebuild 侧，独立第二份语义）。

- 旧侧实锚 `datara-backend/api/model.py:562-577`（`_col_to_field`）
  + `api/model.py:267-283`（`_field_kwargs`）。
- rebuild 落点 `rebuild/model/service.py`（`_col_to_field`）
  + `rebuild/model/repository.py`（`_field_kwargs`）。

对同一 `information_schema.COLUMNS` 行，断言两侧输出 dict **全等**；
并加锁**链路** `行 → _col_to_field → _field_kwargs`（即逆向导入实际消费路径）。

`_col_to_field` 是纯函数（无 DB / 无网络），故差分可脱离数据库运行。
"""

import pytest

pytest.importorskip("api.model")

from api.model import _col_to_field as legacy_col_to_field
from api.model import _field_kwargs as legacy_field_kwargs
from rebuild.model.repository import _field_kwargs as rebuild_field_kwargs
from rebuild.model.service import _col_to_field as rebuild_col_to_field

# COLUMNS 行构造器：位置序 = (COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE,
# COLUMN_DEFAULT, COLUMN_COMMENT, COLUMN_KEY, CHARACTER_MAXIMUM_LENGTH,
# NUMERIC_PRECISION, NUMERIC_SCALE)
COL_KEYS = {"name", "dataType", "length", "precision", "nullable",
            "defaultValue", "comment", "isPk", "isPartition", "dictRef"}


def _col(name, dtype, *, column_type="", nullable="YES", default=None, comment="",
         key="", char_len=None, num_p=None, num_s=None):
    return (name, dtype, column_type, nullable, default, comment, key, char_len, num_p, num_s)


ROWS = {
    "varchar_with_len": _col("c_varchar", "varchar", char_len=64),
    "char_with_len": _col("c_char", "char", char_len=8),
    "decimal_precision_scale": _col("c_decimal", "decimal", num_p=12, num_s=2),
    "numeric_zero_scale": _col("c_numeric", "numeric", num_p=10, num_s=0),
    "int_ignores_numeric_cols": _col("c_int", "int", num_p=11, num_s=0),
    "lowercase_data_type": _col("c_lower", "varchar", char_len=32),
    "upper_data_type": _col("c_upper", "VARCHAR", char_len=16),
    "none_data_type_falls_back": _col("c_none", None, char_len=8),
    "empty_string_data_type_falls_back": _col("c_empty", "", char_len=8),
    "nullable_yes": _col("c_ny", "int", nullable="YES"),
    "nullable_no": _col("c_nn", "int", nullable="NO"),
    "nullable_other_string": _col("c_no2", "int", nullable=""),       # 非 "YES" → False
    "default_zero_string": _col("c_dz", "int", default="0"),
    "default_none": _col("c_dn", "int", default=None),
    "default_empty_string": _col("c_de", "int", default=""),         # falsy 但 is not None → ""
    "default_text": _col("c_dt", "varchar", default="CURRENT_TIMESTAMP"),
    "comment_none": _col("c_cn", "int", comment=None),
    "comment_empty": _col("c_ce", "int", comment=""),
    "comment_text": _col("c_ct", "int", comment="金额（分）"),
    "pk_pri": _col("c_pk", "bigint", key="PRI"),
    "key_uni_not_pk": _col("c_uni", "varchar", key="UNI"),           # 非 "PRI" → False
    "key_empty": _col("c_k0", "varchar", key=""),
    "nulls_everywhere": _col("c_null", None, nullable=None, default=None,
                             comment=None, key=None, char_len=None,
                             num_p=None, num_s=None),
    "decimal_null_precision": _col("c_dnp", "decimal", num_p=None, num_s=None),
    "varchar_null_char_len": _col("c_vnl", "varchar", char_len=None),
}

NAMES = list(ROWS)


@pytest.mark.parametrize("name", NAMES)
def test_col_to_field_matches_legacy(name):
    """两侧对同一 COLUMNS 行输出全等（含键集合）。"""
    row = ROWS[name]
    legacy = legacy_col_to_field(row)
    rebuild = rebuild_col_to_field(row)
    assert set(legacy) == COL_KEYS
    assert rebuild == legacy


@pytest.mark.parametrize("name", NAMES)
def test_col_to_field_then_field_kwargs_chain_matches_legacy(name):
    """链路差分：`行 → _col_to_field → _field_kwargs` 两侧全等（逆向导入实际消费路径）。"""
    row = ROWS[name]
    legacy_chain = legacy_field_kwargs(legacy_col_to_field(row))
    rebuild_chain = rebuild_field_kwargs(rebuild_col_to_field(row))
    assert rebuild_chain == legacy_chain


def test_col_to_field_is_pure_and_repeatable():
    """纯函数：同输入两次调用结果一致（无隐藏状态）。"""
    row = ROWS["decimal_precision_scale"]
    assert rebuild_col_to_field(row) == rebuild_col_to_field(row)
    assert legacy_col_to_field(row) == rebuild_col_to_field(row)

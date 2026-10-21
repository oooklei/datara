"""17.2-17 差分等价测试：`rebuild/model/dsconn.py` 移植件 vs 旧侧 `common/dsconn.py`。

**本文件是迁移保真度的差分锁定件，不是 rebuild 运行时依赖。**
`rebuild/model/dsconn.py` 是旧侧 `common/dsconn.py:23-24,38-62`
（`CONNECT_TIMEOUT` / `DEFAULT_READ_TIMEOUT` / `open_connection`）的逐行移植。

`open_connection` 会**真实建连**，无法直接对拍返回值；故本文件把两侧模块内的
`Connection` 构造器替换为记录器（两侧模块均为 `from pymysql.connections import Connection`
的模块级名字，可独立替换），对同一数据源行断言**连接参数逐键全等** ——
等价于旧侧 `Connection(host=, port=, user=, password=, database=, charset=,
connect_timeout=, read_timeout=, write_timeout=)` 的实参全等。

旧侧不可导入时整体 `importorskip` 跳过（第⑤步下线旧侧后本文件应随迁移收尾一并删除）。
"""

import pytest

pytest.importorskip("common.dsconn", reason="旧侧 common.dsconn 不在导入路径，跳过差分")

import common.dsconn as legacy_mod  # noqa: E402
import rebuild.model.dsconn as new_mod  # noqa: E402


class _Recorder:
    """记录 `Connection(**kwargs)` 实参（不建真连接）。"""

    def __init__(self):
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return kwargs


_UNSET = object()  # 与 `None`（=不限）区分：未指定时须让函数自带缺省值生效


def _connect_kwargs(mod, ds, *, db=None, read_timeout=_UNSET):
    """调用 `mod.open_connection` 并捕获其传给 `Connection` 的实参。"""
    recorder = _Recorder()
    original = mod.Connection
    mod.Connection = recorder
    kwargs = {} if read_timeout is _UNSET else {"read_timeout": read_timeout}
    try:
        mod.open_connection(ds, db=db, **kwargs)
    finally:
        mod.Connection = original
    return recorder.kwargs


def _ds(**over):
    """duck-typed 数据源行（两侧 `open_connection` 只读这 6 个列）。"""
    base = {"type": "mysql", "host": "db.internal", "port": 3306,
            "db_name": "trade", "user": "app", "pwd": "s3cret"}
    base.update(over)
    return type("Ds", (), base)()


# ---------------------------------------------------------------- 连接参数矩阵

_CASES = [
    # (说明, ds 覆盖, 调用覆盖)
    ("mysql 显式端口", _ds(), {}),
    ("mysql 缺省端口回退 3306", _ds(port=None), {}),
    ("greatdb 缺省端口回退 3316", _ds(type="greatdb", port=None), {}),
    ("greatdb 显式端口", _ds(type="greatdb", port=3317), {}),
    ("host 缺省回退 127.0.0.1", _ds(host=None), {}),
    ("user 缺省回退 root", _ds(user=None), {}),
    ("pwd 缺省回退空串", _ds(pwd=None), {}),
    ("db 覆盖数据源 db_name", _ds(), {"db": "other_db"}),
    ("db=None 时用数据源 db_name", _ds(db_name="src_db"), {}),
    ("数据源 db_name 为空 → database=None", _ds(db_name=None), {}),
    ("db 空串 → falsy → 回退数据源库", _ds(db_name="src_db"), {"db": ""}),
    ("read_timeout=None（不限）", _ds(), {"read_timeout": None}),
    ("read_timeout 自定义", _ds(), {"read_timeout": 5}),
]


@pytest.mark.parametrize("label,ds,call", _CASES, ids=[c[0] for c in _CASES])
def test_open_connection_kwargs_match_legacy(label, ds, call):
    """同一数据源行 + 同一调用覆盖 → 两侧传给 `Connection` 的实参**逐键全等**。"""
    legacy_kwargs = _connect_kwargs(legacy_mod, ds, **call)
    new_kwargs = _connect_kwargs(new_mod, ds, **call)
    assert new_kwargs == legacy_kwargs, label


def test_open_connection_timeouts_match_legacy_constants():
    """缺省超时实锚旧侧 `CONNECT_TIMEOUT=5` / `DEFAULT_READ_TIMEOUT=60`。"""
    kwargs = _connect_kwargs(new_mod, _ds())
    assert kwargs["connect_timeout"] == legacy_mod.CONNECT_TIMEOUT == 5
    assert kwargs["read_timeout"] == legacy_mod.DEFAULT_READ_TIMEOUT == 60
    assert kwargs["write_timeout"] == 60  # 旧侧 write_timeout 同 read_timeout
    assert kwargs["charset"] == "utf8mb4"


@pytest.mark.parametrize("bad_type", ["doris", "file", "postgresql", ""])
def test_open_connection_bad_type_matches_legacy(bad_type):
    """非连接型数据源 → 两侧同样 `ValueError` 且 `str()` 文案全等。"""
    ds = _ds(type=bad_type)
    with pytest.raises(ValueError) as new:
        new_mod.open_connection(ds)
    with pytest.raises(ValueError) as old:
        legacy_mod.open_connection(ds)
    assert str(new.value) == str(old.value)

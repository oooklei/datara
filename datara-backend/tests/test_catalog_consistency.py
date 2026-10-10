"""G-19 CI 门禁：组件注册表单一真源一致性校验。

断言：
1. WORKER_TYPES ⊆ EXECUTORS 注册集合（防"前端可拖出但后端找不到执行器"的 P0 复发）
2. MASTER_HANDLER_TYPES ⊇ PASSTHROUGH_TYPES ∪ STREAM_TYPES
3. DISPATCHABLE_EXECUTORS = WORKER_TYPES ∪ STREAM_TYPES
4. 四处后端 WORKER_TYPES 引用均 import 自 components.catalog（无字面量副本）
5. 引擎 handler 字典覆盖 MASTER_HANDLER_TYPES（无遗漏）
"""

from pathlib import Path


# 使用 WORKER_TYPES 的后端模块应全部 import 自 components.catalog
# （dag.py 现仅 import STREAM_TYPES，scheduler.py 重构后不再使用，均已移出清单）
_BACKEND_IMPORTS = [
    "master/engine.py",
    "master/failover.py",
]
# dag.py 从 catalog 导入 STREAM_TYPES（不再用 WORKER_TYPES）；守卫同口径覆盖
_DAG_STREAM_IMPORT = "master/dag.py"


def test_catalog_canonical_definitions():
    """catalog.py 定义的集合自洽。"""
    from components.catalog import (
        DISPATCHABLE_EXECUTORS,
        MASTER_HANDLER_TYPES,
        PASSTHROUGH_TYPES,
        STREAM_TYPES,
        WORKER_TYPES,
    )

    # worker 集是分派集的子集
    assert WORKER_TYPES.issubset(DISPATCHABLE_EXECUTORS)
    # 分派集 = worker ∪ 流节点
    assert DISPATCHABLE_EXECUTORS == WORKER_TYPES | STREAM_TYPES
    # master handler 覆盖直通 + 流
    assert PASSTHROUGH_TYPES.issubset(MASTER_HANDLER_TYPES)
    assert STREAM_TYPES.issubset(MASTER_HANDLER_TYPES)
    # 无交集（一个节点不能同时是 worker 和 master handler）
    assert not (WORKER_TYPES & MASTER_HANDLER_TYPES)


def test_worker_types_all_registered():
    """每个 worker 类型都必须在 worker/executor.py 的 EXECUTORS 中注册。

    这是防 G-1 流节点缺陷复发的核心门禁：新增 worker 组件时，若只改 catalog 而
    忘记 @register，本测试即红。
    """
    from components.catalog import WORKER_TYPES
    from worker.executor import EXECUTORS

    registered = set(EXECUTORS.keys())
    missing = WORKER_TYPES - registered
    assert not missing, f"WORKER_TYPES 中 {missing} 未在 worker/executor.py @register"


def test_backend_files_import_from_catalog():
    """四处后端模块必须 import 自 components.catalog，不得内联字面量副本。"""
    repo_root = Path(__file__).resolve().parent.parent
    for rel in _BACKEND_IMPORTS:
        text = (repo_root / rel).read_text(encoding="utf-8")
        # 不得出现内联字面量定义
        assert 'WORKER_TYPES = ("sql"' not in text, f"{rel} 存在内联 WORKER_TYPES 字面量副本"
        assert "WORKER_TYPES = frozenset({'sql'" not in text, f"{rel} 存在内联 WORKER_TYPES 字面量副本"
        # 必须 import 自 catalog（G-14：dag.py 额外导入 STREAM_TYPES，允许同行）
        assert "from components.catalog import" in text and "WORKER_TYPES" in text, (
            f"{rel} 未从 components.catalog 导入 WORKER_TYPES"
        )
    # dag.py 同口径：类型集合必须 import 自真源（当前仅 STREAM_TYPES）
    dag_text = (repo_root / _DAG_STREAM_IMPORT).read_text(encoding="utf-8")
    assert "WORKER_TYPES = " not in dag_text, "dag.py 不得内联 WORKER_TYPES 字面量副本"
    assert "from components.catalog import STREAM_TYPES" in dag_text, (
        "dag.py 的 STREAM_TYPES 必须从 components.catalog 导入"
    )


def test_engine_handler_covers_master_types():
    """引擎 handler 字典必须覆盖 MASTER_HANDLER_TYPES 全集（无遗漏）。"""
    from components.catalog import MASTER_HANDLER_TYPES
    from master.engine import WorkflowExecuteRunnable

    # 通过 _execute_node 的 handler 字典反查（源码静态解析）
    import inspect

    src = inspect.getsource(WorkflowExecuteRunnable._execute_node)
    # handler = { "start": ..., "end": ..., ... }.get(node_type)
    # 简单断言：每个 MASTER_HANDLER_TYPES 成员都在源码中被引用为字典 key
    for t in sorted(MASTER_HANDLER_TYPES):
        assert f'"{t}": self._' in src or f"'{t}': self._" in src, (
            f"MASTER_HANDLER_TYPES 中 {t} 未在引擎 handler 字典中注册"
        )


def test_dispatachable_matches_catalog():
    """api/component_design.py 的 DISPATCHABLE_EXECUTORS 必须与 catalog 同步。"""
    from components.catalog import DISPATCHABLE_EXECUTORS as CATALOG_DISPATCHABLE
    from api.component_design import DISPATCHABLE_EXECUTORS

    assert DISPATCHABLE_EXECUTORS == CATALOG_DISPATCHABLE


def test_smoke_registered_in_worker_types():
    """G-12：smoke 必须在 WORKER_TYPES 中且后端 executor 已注册（补 palette 入口的前提）。"""
    from components.catalog import WORKER_TYPES
    from worker.executor import EXECUTORS

    assert "smoke" in WORKER_TYPES
    assert "smoke" in EXECUTORS, "smoke 未在 worker/executor.py @register"


def test_deprecated_types_marked():
    """G-24：src_select/tgt_select 已彻底删除（用户要求），不在 PASSTHROUGH_TYPES 中。"""
    from components.catalog import PASSTHROUGH_TYPES, is_deprecated_type

    # src_select/tgt_select 已彻底删除，不再保留
    assert not is_deprecated_type("src_select")
    assert not is_deprecated_type("tgt_select")
    # 不在 PASSTHROUGH_TYPES 中（已删除）
    assert "src_select" not in PASSTHROUGH_TYPES
    assert "tgt_select" not in PASSTHROUGH_TYPES
    # 未被标记为废弃的其他类型
    assert not is_deprecated_type("endpoint_select")
    assert not is_deprecated_type("field_map")

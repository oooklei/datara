"""组件目录单一真源（G-19 落地）：WORKER_TYPES / MASTER_HANDLER_TYPES / PASSTHROUGH_TYPES /
STREAM_TYPES / NON_EXECUTABLE_TYPES 统一定义，各模块 import 使用，消除 4-7 处字面量副本。

口径对齐：
- WORKER_TYPES：派发到 worker 执行器的节点（与 worker/executor.py @register 装饰器一一对应）
- MASTER_HANDLER_TYPES：master 内联 handler 字典可路由的节点（含逻辑/直通/流/页面）
- PASSTHROUGH_TYPES：自身不执行、配置被下游拍平的节点（endpoint_select/field_map/...）
- STREAM_TYPES：常驻流作业算子（数据面由 worker/stream 承载，批引擎仅状态占位）
- NON_EXECUTABLE_TYPES：不产生任务实例的展示型节点（page_board）

CI 门禁（tests/test_catalog_consistency.py）断言：
1. WORKER_TYPES ⊆ EXECUTORS 注册集合（防"前端可拖出但后端找不到执行器"的 P0 复发）
2. MASTER_HANDLER_TYPES ⊇ WORKER_TYPES ∪ PASSTHROUGH_TYPES ∪ STREAM_TYPES ∪ NON_EXECUTABLE_TYPES
3. 节点 type 全集 = MASTER_HANDLER_TYPES ∪ WORKER_TYPES ∪ 模板类型（demo_pipeline/src_base_orch/...）
"""

# ---- worker 执行器（派发 → Redis Stream → worker）----
WORKER_TYPES = frozenset(
    {
        "sql",
        "shell",
        "python",
        "ssh",
        "smoke",
        "procedure",
        "http",
        "file",
        "sync",
        "file_sync",
        "notify",
        # M-B2 ETL 执行器（17 个）
        "src_db",
        "src_file",
        "out_db",
        "out_file",
        "op_filter",
        "op_join",
        "op_expr",
        "op_agg",
        "op_dedup",
        "op_select",
        "op_sort",
        "op_split",
        "op_merge",
        "op_replace",
        "op_sample",
        "op_udf",
        "op_script",
        # M-B2 Stream 执行器（9 个，op_script 共享）
        "s_kafka",
        "s_cdc",
        "p_filter",
        "p_join",
        "p_window",
        "op_cep",
        "o_doris",
        "o_kafka",
        "o_alert",
    }
)

# ---- master 内联 handler 字典可路由节点 ----
# 逻辑控制（12）
_MASTER_LOGIC = frozenset(
    {
        "start",
        "end",
        "conditions",
        "switch",
        "fork",
        "join",
        "merge",
        "delay",
        "dependent",
        "loop",
        "variable",
        "assert",
    }
)
# 直通配置（5）：自身不执行，配置被下游拍平/消费
# src_select/tgt_select 已废弃（依托 endpoint_select 实现），从 PASSTHROUGH_TYPES 移除
PASSTHROUGH_TYPES = frozenset(
    {
        "field_map",
        "field_map_union",
        "condition_set",
        "endpoint_select",
        "page_board",  # G-17：渲染型节点，passthrough SUCCESS
    }
)
# 常驻流算子（3）：批引擎仅状态占位，数据面由 worker/stream 承载
STREAM_TYPES = frozenset(
    {
        "stream_input",
        "stream_fuse",
        "stream_output",
    }
)
# 展示型节点（1）：不产生任务实例
NON_EXECUTABLE_TYPES = frozenset(
    {
        "page_board",
    }
)

# G-24：已废弃类型（历史兼容保留一个版本周期，待历史工作流迁移到 endpoint_select 后移除）
# src_select/tgt_select 已彻底删除（依托 endpoint_select 实现），不再保留
_DEPRECATED_TYPES = frozenset()

MASTER_HANDLER_TYPES = frozenset(_MASTER_LOGIC | PASSTHROUGH_TYPES | STREAM_TYPES)

# ---- 模板类型（落图即展开，无独立运行时路由）----
TEMPLATE_TYPES = frozenset(
    {
        "demo_pipeline",
        "src_base_orch",
        "tgt_base_orch",
        "file_sync_orch",
    }
)

# ---- 全量可拖出节点（palette 渲染集合 = MASTER_HANDLER_TYPES - runtimeOnly - 模板）----
# runtimeOnly 执行节点（sync/file_sync）由 materialize_sync_exec 物化进运行图，设计态不落地
RUNTIME_ONLY_TYPES = frozenset({"sync", "file_sync"})

# ---- 可执行节点全集（MASTER 路由 ∪ WORKER 派发 ∪ 运行时物化节点）----
ALL_EXECUTABLE_TYPES = frozenset(MASTER_HANDLER_TYPES | WORKER_TYPES | RUNTIME_ONLY_TYPES)

# ---- 发布闸门用：可分派执行器（worker ∪ 流节点）----
# 对齐 api/component_design.py DISPATCHABLE_EXECUTORS（原 WORKER_TYPES | {stream三节点}）
DISPATCHABLE_EXECUTORS = frozenset(WORKER_TYPES | STREAM_TYPES)


def is_worker_type(node_type: str) -> bool:
    return node_type in WORKER_TYPES


def is_master_type(node_type: str) -> bool:
    return node_type in MASTER_HANDLER_TYPES


def is_executable(node_type: str) -> bool:
    return node_type in ALL_EXECUTABLE_TYPES


def is_stream_type(node_type: str) -> bool:
    return node_type in STREAM_TYPES


def is_template_type(node_type: str) -> bool:
    return node_type in TEMPLATE_TYPES


def is_deprecated_type(node_type: str) -> bool:
    """G-24：已废弃类型（历史兼容保留，新工作流不应再引用）。"""
    return node_type in _DEPRECATED_TYPES

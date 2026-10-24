"""Runtime materialization for SYNC endpoint selections.

Design-time SYNC graphs contain declarative ``endpoint_select`` nodes.  The
runtime receives concrete execution nodes instead; this module keeps that
translation deterministic and side-effect free so the engine can test it
before opening any datasource connection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class SyncMaterializationError(ValueError):
    """Raised when an endpoint selection cannot be made executable."""


_MODES = {"src_base", "tgt_base", "file_sync"}


def materialize_endpoint_nodes(nodes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return runtime-only execution nodes for declarative endpoint selectors.

    Non-selector design nodes are preserved by value.  Each selector expands to
    one ``sys_exec_<node_code>`` node with a normalized ``baseMode`` and the
    original endpoint parameters.  Invalid or ambiguous selectors fail closed.
    """

    result: list[dict[str, Any]] = []
    for raw in nodes:
        node = dict(raw)
        node_type = str(node.get("node_type") or node.get("type") or "")
        if node_type.lower() != "endpoint_select":
            result.append(node)
            continue
        node_code = str(node.get("node_code") or node.get("code") or "").strip()
        if not node_code:
            raise SyncMaterializationError("endpoint_select requires node_code")
        params = node.get("params")
        if not isinstance(params, Mapping):
            raise SyncMaterializationError(f"endpoint_select {node_code!r} requires params")
        if "baseMode" in params and "base_mode" in params and params["baseMode"] != params["base_mode"]:
            raise SyncMaterializationError(f"endpoint_select {node_code!r} has conflicting baseMode values")
        mode = params.get("baseMode", params.get("base_mode"))
        if mode not in _MODES:
            raise SyncMaterializationError(f"endpoint_select {node_code!r} has unsupported baseMode")
        runtime_type = "file_sync" if mode == "file_sync" else "sync"
        result.append({
            "node_code": f"sys_exec_{node_code}",
            "node_type": runtime_type,
            "runtime_only": True,
            "source_node_code": node_code,
            "params": {**dict(params), "baseMode": mode},
        })
    return result

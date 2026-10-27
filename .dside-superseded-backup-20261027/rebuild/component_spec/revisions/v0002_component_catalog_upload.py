"""Declare the versioned resource-upload capability for executable components.

Increment 7 / 会议纪要④（设计 §5A.7）：SQL 组件支持上传文件，Python、Shell
脚本组件支持上传脚本文件。该能力以「资源版本引用」的形式声明在组件 spec 的
八段 form DSL 中：

- ``form.params.sourceMode``  —— 内容来源（inline / resource）
- ``form.params.resourceRef`` —— 资源版本引用（uiType=resource，cap 承载
  mode/kind/extensions/versioned/allowLatest）
- ``form.conditions.c-resource-mode`` —— 当 sourceMode=resource 时显示 resourceRef

历史实现把该声明放在 seed 脚本 ``scripts/seed_rebuild_component_catalog.py``
的 ``_normalize_spec_json`` 里，属于「演示数据灌入」而非「结构性保证」。本迁移
（revision ``i4_0002_component_catalog_upload``）把 upload 能力收敛为**版本化
数据迁移**：对已存在的 sql/python/shell 组件版本行补齐 upload 声明并重算
``spec_hash``，使 upload 能力不再依赖 seed 灌数据。

幂等策略：
- 仅当 ``form.params`` 缺 ``sourceMode`` / ``resourceRef``、或 ``form.conditions``
  缺 ``c-resource-mode`` 时才写入；已具备则原样保留。
- 同一 revision 重复执行由 ``MigrationRunner`` 台账（``SchemaMigrationRecord``）
  记为 skipped，不会二次改写。

边界（部署顺序）：
- 本迁移在应用启动时（``rebuild/api/app.py``）执行，早于 seed。fresh DB 首次
  执行时 ``t_component_version`` 为空，升级为 no-op；seed 随后灌入已归一化的
  演示数据。
- ``validate_schema`` 对**所有** sql/python/shell 版本行做 upload 声明存在性 +
  形状校验（fail-closed）：seed 归一化后的行通过；若出现缺失/损坏的 upload 声明，
  启动即拒绝，避免「结构性能力靠灌数据兜底」的隐患。
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import Engine, inspect, text

from rebuild.component_spec.catalogue import FORM_SECTIONS


revision = "i4_0002_component_catalog_upload"

# 可执行数据组件：upload 能力仅对这三类声明（与 seed 的 resource_kind 映射一致）。
EXECUTABLE_TYPES = ("sql", "python", "shell")
RESOURCE_EXTENSIONS = {
    "sql": [".sql"],
    "python": [".py", ".zip"],
    "shell": [".sh", ".bash"],
}

MANIFEST = {
    "revision": revision,
    "table": "t_component_version",
    "executable_types": list(EXECUTABLE_TYPES),
    "declaration": {
        "form.params.sourceMode": "select(inline/resource), default=inline",
        "form.params.resourceRef": "uiType=resource, cap.mode=resource, cap.kind=<type>, cap.versioned=true, cap.allowLatest=false",
        "form.conditions.c-resource-mode": "when sourceMode eq resource -> show resourceRef",
    },
    "idempotent": True,
    "guarantee": "upload capability is structurally guaranteed by this revision, not by the seed script",
}
checksum = "aa96bb50bb868997d2b7986d47cb927156a616fa622f3ab4d7e56da3a309fa0f"


def _source_mode_param() -> dict:
    return {
        "key": "sourceMode",
        "label": "内容来源",
        "uiType": "select",
        "required": True,
        "visible": True,
        "default": "inline",
        "options": [
            {"label": "内联内容", "value": "inline"},
            {"label": "资源版本", "value": "resource"},
        ],
    }


def _resource_ref_param(type_name: str) -> dict:
    return {
        "key": "resourceRef",
        "label": "资源版本",
        "uiType": "resource",
        "required": False,
        "visible": True,
        "cap": {
            "mode": "resource",
            "kind": type_name,
            "extensions": list(RESOURCE_EXTENSIONS[type_name]),
            "versioned": True,
            "allowLatest": False,
        },
    }


def _resource_mode_condition() -> dict:
    return {
        "id": "c-resource-mode",
        "when": {"field": "sourceMode", "op": "eq", "value": "resource"},
        "show": ["resourceRef"],
    }


def _ensure_upload(spec: dict, type_name: str) -> bool:
    """Return True when the canonical upload declaration was added or repaired."""
    changed = False
    form = spec.get("form")
    if not isinstance(form, dict):
        form = {section: [] for section in FORM_SECTIONS}
        spec["form"] = form
        changed = True
    for section in FORM_SECTIONS:
        if not isinstance(form.get(section), list):
            form[section] = []
            changed = True
    params = form["params"]
    keys = {item.get("key") for item in params if isinstance(item, dict)}
    if "sourceMode" not in keys:
        params.append(_source_mode_param())
        changed = True
    if "resourceRef" not in keys:
        params.append(_resource_ref_param(type_name))
        changed = True
    if not any(
        isinstance(item, dict) and item.get("id") == "c-resource-mode"
        for item in form["conditions"]
    ):
        form["conditions"].append(_resource_mode_condition())
        changed = True
    return changed


def _spec_hash(spec: dict) -> str:
    """Canonical content hash; mirrors api/component_design.py::_spec_hash."""
    canonical = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upgrade(engine: Engine) -> None:
    """Idempotently add the upload declaration to executable component versions."""
    if "t_component_version" not in set(inspect(engine).get_table_names()):
        return
    placeholders = ", ".join(f":t{index}" for index in range(len(EXECUTABLE_TYPES)))
    bindings = {f"t{index}": type_name for index, type_name in enumerate(EXECUTABLE_TYPES)}
    with engine.begin() as connection:
        rows = connection.execute(
            text(f"SELECT id, type, spec_json FROM t_component_version WHERE type IN ({placeholders})"),
            bindings,
        ).mappings().all()
        for row in rows:
            type_name = (row["type"] or "").lower()
            if type_name not in EXECUTABLE_TYPES:
                continue
            try:
                spec = json.loads(row["spec_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(spec, dict):
                continue
            if not _ensure_upload(spec, type_name):
                continue
            new_json = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
            connection.execute(
                text("UPDATE t_component_version SET spec_json=:spec_json, spec_hash=:spec_hash WHERE id=:id"),
                {"spec_json": new_json, "spec_hash": _spec_hash(spec), "id": row["id"]},
            )


def _require_upload_declaration(type_name: str, spec: dict) -> None:
    form = spec.get("form")
    if not isinstance(form, dict):
        raise RuntimeError(f"executable component {type_name} is missing the form declaration")
    params = form.get("params")
    if not isinstance(params, list):
        raise RuntimeError(f"executable component {type_name} is missing form.params")
    by_key = {item.get("key"): item for item in params if isinstance(item, dict)}
    source_mode = by_key.get("sourceMode")
    if not isinstance(source_mode, dict) or source_mode.get("default") != "inline":
        raise RuntimeError(f"executable component {type_name} is missing the sourceMode upload declaration")
    resource_ref = by_key.get("resourceRef")
    if not isinstance(resource_ref, dict) or resource_ref.get("uiType") != "resource":
        raise RuntimeError(f"executable component {type_name} is missing the resourceRef upload declaration")
    cap = resource_ref.get("cap")
    if not isinstance(cap, dict):
        raise RuntimeError(f"executable component {type_name} has a malformed resourceRef capability")
    if cap.get("mode") != "resource" or cap.get("kind") != type_name:
        raise RuntimeError(f"executable component {type_name} has a mismatched resourceRef capability")
    if cap.get("versioned") is not True or cap.get("allowLatest") is not False:
        raise RuntimeError(f"executable component {type_name} must reference a versioned, non-latest resource")
    extensions = cap.get("extensions")
    if not isinstance(extensions, list) or not set(RESOURCE_EXTENSIONS[type_name]) <= set(extensions):
        raise RuntimeError(f"executable component {type_name} has invalid resourceRef extensions")
    conditions = form.get("conditions")
    if not isinstance(conditions, list) or not any(
        isinstance(item, dict) and item.get("id") == "c-resource-mode" for item in conditions
    ):
        raise RuntimeError(f"executable component {type_name} is missing the c-resource-mode condition")


def validate_schema(engine: Engine) -> None:
    """Fail closed when any executable version lacks the upload declaration."""
    if "t_component_version" not in set(inspect(engine).get_table_names()):
        raise RuntimeError("component catalog migration is recorded but t_component_version is missing")
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT type, spec_json FROM t_component_version WHERE type IN ('sql','python','shell')")
        ).mappings().all()
    for row in rows:
        type_name = (row["type"] or "").lower()
        try:
            spec = json.loads(row["spec_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"executable component {type_name} has invalid spec_json") from error
        if not isinstance(spec, dict):
            raise RuntimeError(f"executable component {type_name} spec_json must be an object")
        _require_upload_declaration(type_name, spec)

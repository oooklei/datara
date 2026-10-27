"""Publish the four governed stream components when legacy seed data omitted them."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import Engine, inspect, text

from rebuild.component_spec.catalogue import FORM_SECTIONS, validate_declaration


revision = "i4_0003_stream_component_catalog"
checksum = "e090962f146e311eccb0c53853c4d63d04bf5c9a017e945655f560892b4210ee"
STREAM_COMPONENT_TYPES = ("stream_input", "stream_fuse", "stream_output", "page_board")


def _field(key: str, label: str, ui_type: str, **extra: Any) -> dict[str, Any]:
    return {"key": key, "label": label, "uiType": ui_type, "visible": True, **extra}


def _form(params: list[dict[str, Any]], conditions: list[dict[str, Any]] | None = None) -> dict[str, list[Any]]:
    form: dict[str, list[Any]] = {section: [] for section in FORM_SECTIONS}
    form["params"] = params
    form["conditions"] = conditions or []
    return form


def _specs() -> dict[str, dict[str, Any]]:
    return {
        "stream_input": {
            "specVersion": 1,
            "summary": "实时流输入，支持内置电商模拟数据与已注册流数据源。",
            "category": "stream",
            "icon": "input",
            "color": "#0891b2",
            "ports": {"outputs": [{"id": "events", "label": "事件流"}]},
            "form": _form([
                _field("srcType", "来源类型", "select", required=True, default="simulate", options=[
                    {"label": "模拟数据", "value": "simulate"},
                    {"label": "Kafka", "value": "kafka"},
                    {"label": "CDC", "value": "cdc"},
                    {"label": "HTTP", "value": "http"},
                    {"label": "文件尾随", "value": "file"},
                    {"label": "Redis Stream", "value": "redis"},
                    {"label": "MQTT", "value": "mqtt"},
                ]),
                _field("simDataset", "内置数据集", "select", default="ecommerce", options=[
                    {"label": "电商", "value": "ecommerce"},
                    {"label": "IoT", "value": "iot"},
                    {"label": "访问分析", "value": "visit"},
                ]),
                _field("simEvents", "事件过滤", "text", required=False),
                _field("simEps", "事件速率（条/秒）", "number", default=5),
            ], [{"id": "simulate-fields", "when": {"field": "srcType", "op": "eq", "value": "simulate"}, "show": ["simDataset", "simEvents", "simEps"]}]),
        },
        "stream_fuse": {
            "specVersion": 1,
            "summary": "实时流融合、过滤、映射与窗口聚合。",
            "category": "stream",
            "icon": "merge",
            "color": "#0f766e",
            "ports": {"inputs": [{"id": "left", "label": "左流"}, {"id": "right", "label": "右流"}], "outputs": [{"id": "events", "label": "融合流"}]},
            "form": _form([
                _field("fuseType", "融合类型", "select", required=True, default="window", options=[
                    {"label": "归并", "value": "union"}, {"label": "关联", "value": "join"},
                    {"label": "窗口聚合", "value": "window"}, {"label": "过滤", "value": "filter"},
                    {"label": "字段映射", "value": "map"},
                ]),
                _field("groupKeys", "分组键", "text", required=False),
                _field("aggs", "聚合函数", "rows", required=False),
                _field("windowType", "窗口类型", "select", default="tumbling", options=[
                    {"label": "滚动窗口", "value": "tumbling"}, {"label": "滑动窗口", "value": "sliding"},
                ]),
                _field("windowSizeSec", "窗口大小（秒）", "number", default=60),
                _field("watermarkSec", "水位线延迟（秒）", "number", default=5),
            ], [{"id": "window-fields", "when": {"field": "fuseType", "op": "eq", "value": "window"}, "show": ["groupKeys", "aggs", "windowType", "windowSizeSec", "watermarkSec"]}]),
        },
        "stream_output": {
            "specVersion": 1,
            "summary": "实时结果输出并提供轮询、SSE 与看板观摩数据。",
            "category": "stream",
            "icon": "output",
            "color": "#059669",
            "ports": {"inputs": [{"id": "events", "label": "事件流"}]},
            "form": _form([
                _field("outType", "输出通道", "select", required=True, default="api", options=[
                    {"label": "API 订阅", "value": "api"}, {"label": "目标表", "value": "table"},
                    {"label": "Kafka", "value": "kafka"}, {"label": "滚动文件", "value": "file"},
                ]),
                _field("keepLast", "保留最近记录数", "number", default=100),
                _field("schemaText", "字段声明", "text", required=False),
            ], [{"id": "api-fields", "when": {"field": "outType", "op": "eq", "value": "api"}, "show": ["keepLast", "schemaText"]}]),
        },
        "page_board": {
            "specVersion": 1,
            "summary": "实时数据观摩看板，展示指标、趋势、分布和明细。",
            "category": "stream",
            "icon": "dashboard",
            "color": "#0e7490",
            "form": _form([
                _field("preset", "看板模板", "select", required=True, default="ecommerce", options=[
                    {"label": "电商实时大盘", "value": "ecommerce"}, {"label": "IoT 设备监控", "value": "iot"},
                    {"label": "访问分析", "value": "visit"}, {"label": "自定义", "value": "custom"},
                ]),
                _field("boardLayout", "布局模式", "select", default="auto", options=[
                    {"label": "自适应", "value": "auto"}, {"label": "指标卡", "value": "metrics"},
                    {"label": "趋势", "value": "trend"}, {"label": "完整大盘", "value": "full"},
                ]),
            ]),
        },
    }


def _hash(spec: dict[str, Any]) -> str:
    canonical = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upgrade(engine: Engine) -> None:
    if not {"t_component", "t_component_version"} <= set(inspect(engine).get_table_names()):
        return
    metadata = {
        "stream_input": ("流输入", True, "stream_input"),
        "stream_fuse": ("流融合", True, "stream_fuse"),
        "stream_output": ("流输出", True, "stream_output"),
        "page_board": ("实时观摩看板", False, None),
    }
    with engine.begin() as connection:
        next_component_id = max(
            900_000_000,
            connection.execute(text("select coalesce(max(id),0) + 1 from t_component")).scalar_one(),
        )
        next_version_id = max(
            900_000_000,
            connection.execute(text("select coalesce(max(id),0) + 1 from t_component_version")).scalar_one(),
        )
        has_log = "t_component_log" in set(inspect(engine).get_table_names())
        next_log_id = (
            connection.execute(text("select coalesce(max(id),0) + 1 from t_component_log")).scalar_one()
            if has_log else 900_000_000
        )
        next_log_id = max(900_000_000, next_log_id)
        for type_name, spec in _specs().items():
            existing = connection.execute(
                text("select id, published_version from t_component where type=:type"), {"type": type_name}
            ).mappings().first()
            if existing is None:
                name, executable, executor = metadata[type_name]
                connection.execute(text(
                    "insert into t_component "
                    "(id,type,name,category,profile,scope,execution_model,executor,executable,state,published_version,draft_rev,description,create_time,update_time) "
                    "values (:id,:type,:name,'stream','stream','builtin',:model,:executor,:executable,'published',1,0,:description,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), {"id": next_component_id, "type": type_name, "name": name, "model": "dag-engine" if executable else "canvas-device", "executor": executor, "executable": executable, "description": spec["summary"]})
                component_id = next_component_id
                next_component_id += 1
                version = 1
            else:
                component_id = existing["id"]
                version = existing["published_version"] or 1
            version_exists = connection.execute(text(
                "select 1 from t_component_version where component_id=:component_id and version=:version"
            ), {"component_id": component_id, "version": version}).first()
            if version_exists is None:
                encoded = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
                digest = _hash(spec)
                connection.execute(text(
                    "insert into t_component_version "
                    "(id,component_id,type,version,state,spec_json,spec_hash,remark,published_by,published_time,create_time,update_time) "
                    "values (:id,:component_id,:type,:version,'published',:spec_json,:spec_hash,:remark,'system-migration',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), {"id": next_version_id, "component_id": component_id, "type": type_name, "version": version, "spec_json": encoded, "spec_hash": digest, "remark": revision})
                next_version_id += 1
                if has_log:
                    connection.execute(text(
                        "insert into t_component_log "
                        "(id,component_id,type,version,action,spec_hash,operator,remark,operate_time,create_time,update_time) "
                        "values (:id,:component_id,:type,:version,'publish',:spec_hash,'system-migration',:remark,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                    ), {"id": next_log_id, "component_id": component_id, "type": type_name, "version": version, "spec_hash": digest, "remark": revision})
                    next_log_id += 1
            connection.execute(text(
                "update t_component set state='published', published_version=:version, update_time=CURRENT_TIMESTAMP where id=:id"
            ), {"version": version, "id": component_id})


def validate_schema(engine: Engine) -> None:
    if "t_component" not in set(inspect(engine).get_table_names()):
        raise RuntimeError("stream component migration is recorded but t_component is missing")
    placeholders = ",".join(f":t{index}" for index in range(len(STREAM_COMPONENT_TYPES)))
    bindings = {f"t{index}": value for index, value in enumerate(STREAM_COMPONENT_TYPES)}
    with engine.connect() as connection:
        rows = connection.execute(text(
            "select c.type, v.spec_json from t_component c join t_component_version v "
            "on v.component_id=c.id and v.version=c.published_version and v.state='published' "
            f"where c.state='published' and c.type in ({placeholders})"
        ), bindings).mappings().all()
    if {row["type"] for row in rows} != set(STREAM_COMPONENT_TYPES):
        raise RuntimeError("published stream component catalogue is incomplete")
    for row in rows:
        spec = json.loads(row["spec_json"])
        violations = validate_declaration(spec)
        if violations:
            raise RuntimeError(f"invalid stream component {row['type']}: {'; '.join(violations)}")

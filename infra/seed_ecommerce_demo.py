#!/usr/bin/env python3
"""Idempotently prepare the user-visible ecommerce governance demo on 1.9."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_NAME = "电商数据全域治理项目"


def build_blueprints() -> list[dict[str, Any]]:
    return [
        {
            "name": "电商订单离线加工样例",
            "description": "SQL 抽取 → Python 质量处理 → Shell 归档 → 依赖闸门",
            "workflow_type": "NORMAL",
            "nodes": [
                {"code": "sql_extract_orders", "type": "sql", "name": "抽取订单", "params": {"sourceMode": "inline", "sql": "SELECT order_id, user_id, amount, order_time FROM ods_orders WHERE amount >= 0"}},
                {"code": "python_quality", "type": "python", "name": "订单质量处理", "params": {"sourceMode": "inline", "script": "print('validate amount, currency and order_time')"}},
                {"code": "shell_archive", "type": "shell", "name": "归档批次", "params": {"sourceMode": "inline", "script": "printf 'archive ecommerce order batch\\n'"}},
                {"code": "dependency_gate", "type": "dependent", "name": "上游成功依赖", "params": {}},
            ],
        },
        {
            "name": "电商订单同步入仓样例",
            "description": "同步编排七组件表单样例；设计态不使用 runtimeOnly sync/file_sync",
            "workflow_type": "SYNC",
            "nodes": [
                {"code": "source_base", "type": "src_base_orch", "name": "来源基础配置", "params": {"schema": "ecommerce", "object": "orders"}},
                {"code": "endpoint", "type": "endpoint_select", "name": "端点选择", "params": {"baseMode": "src_base", "srcTable": "orders", "tgtTable": "dwd_trade_order"}},
                {"code": "mapping", "type": "field_map", "name": "字段映射", "params": {"fieldMap": [{"from": "order_id", "to": "order_id"}, {"from": "amount", "to": "order_amount"}]}},
                {"code": "mapping_union", "type": "field_map_union", "name": "合并映射", "params": {"inputs": ["endpoint:sourceRef", "endpoint:targetRef"]}},
                {"code": "conditions", "type": "condition_set", "name": "有效订单条件", "params": {"conditions": [{"field": "amount", "operator": ">=", "value": "0"}]}},
                {"code": "target_base", "type": "tgt_base_orch", "name": "目标基础配置", "params": {"schema": "dw", "object": "dwd_trade_order"}},
                {"code": "file_route", "type": "file_sync_orch", "name": "文件同步模式", "params": {"path": "/datara/files/ecommerce/orders.csv"}},
            ],
        },
        {
            "name": "电商实时订单流观摩样例",
            "description": "实时生产订单事件，完成聚合、融合、输出与观摩",
            "workflow_type": "STREAM",
            "nodes": [
                {"code": "order_stream", "type": "stream_input", "name": "实时订单生产", "params": {"sourceMode": "simulate", "scenario": "ecommerce", "simEps": 5}},
                {"code": "order_fuse", "type": "stream_fuse", "name": "订单窗口聚合融合", "params": {"windowSeconds": 10, "groupBy": ["user_id"], "aggregations": [{"field": "amount", "op": "sum", "alias": "amount_sum"}]}},
                {"code": "order_output", "type": "stream_output", "name": "实时结果输出", "params": {"sink": "observation"}},
                {"code": "observation", "type": "page_board", "name": "实时工作流观摩", "params": {"refreshSeconds": 2}},
            ],
        },
    ]


class HttpApi:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"token": token, "Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    @staticmethod
    def _unwrap(response: requests.Response) -> Any:
        payload = response.json()
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {payload.get('msg') or payload.get('message')}")
        if isinstance(payload, dict) and payload.get("code") == 0:
            return payload.get("data")
        return payload

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._unwrap(self.session.get(self.base_url + path, params=params, timeout=30))

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self._unwrap(self.session.post(self.base_url + path, json=body, timeout=30))


def _project_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    return list(payload.get("list", [])) if isinstance(payload, dict) else []


def reconcile_demo(api: Any) -> dict[str, Any]:
    projects = _project_rows(api.get("/api/v1/rebuild/projects"))
    project = next((row for row in projects if row.get("name") == PROJECT_NAME), None)
    if project is None:
        project = api.post("/api/v1/rebuild/projects", {
            "name": PROJECT_NAME,
            "description": "预置电商数据治理、开发、同步与实时流观摩项目",
        })
    project_id = int(project["id"])
    existing = {row["name"]: row for row in api.get("/api/v1/rebuild/workflows", {"project_id": project_id})}
    workflow_ids: dict[str, int] = {}

    for blueprint in build_blueprints():
        versions_payload = api.get("/api/v1/rebuild/components/spec", {"workflow_type": blueprint["workflow_type"]})
        versions = {row["type"]: int(row["publishedVersion"]) for row in versions_payload["items"]}
        workflow = existing.get(blueprint["name"])
        if workflow is None:
            workflow = api.post("/api/v1/rebuild/workflows", {
                "project_id": project_id,
                "name": blueprint["name"],
                "description": blueprint["description"],
                "workflow_type": blueprint["workflow_type"],
            })
        workflow_id = int(workflow["definition_id"])
        workflow_ids[blueprint["workflow_type"]] = workflow_id
        x = 80
        for node in blueprint["nodes"]:
            api.post(f"/api/v1/rebuild/workflows/{workflow_id}/nodes", {
                "project_id": project_id,
                "node_code": node["code"],
                "node_type": node["type"],
                "name": node["name"],
                "component_ref": {"type": node["type"], "version": versions[node["type"]]},
                "params": node["params"],
                "position_x": x,
                "position_y": 160,
            })
            x += 230
        for left, right in zip(blueprint["nodes"], blueprint["nodes"][1:]):
            api.post(f"/api/v1/rebuild/workflows/{workflow_id}/edges", {
                "project_id": project_id,
                "from_node": left["code"],
                "to_node": right["code"],
            })

    jobs = api.get("/api/v1/rebuild/stream/jobs", {"project_id": project_id})
    stream_workflow_id = workflow_ids["STREAM"]
    job = next((row for row in jobs if row.get("workflow_id") == stream_workflow_id), None)
    job_created = job is None
    if job is None:
        job = api.post("/api/v1/rebuild/stream/jobs", {
            "project_id": project_id,
            "name": "电商实时订单流观摩",
            "workflow_id": stream_workflow_id,
            "mq_topic": "datara.demo.ecommerce.orders",
            "runtime_config": {"mode": "fixed_rate", "rows_per_sec": 5, "columns": ["order_id", "user_id", "amount", "region"]},
        })
    return {
        "project_id": project_id,
        "project_name": PROJECT_NAME,
        "workflow_ids": workflow_ids,
        "stream_job_id": int(job["id"]),
        "stream_job_created": job_created,
        "stream_job_state": str(job.get("state") or "CREATED").upper(),
    }


def prime_stream_observation(api: HttpApi, result: dict[str, Any]) -> None:
    job_id = result["stream_job_id"]
    state = str(result.get("stream_job_state") or "CREATED").upper()
    if state in {"CREATED", "STOPPED", "FAILED"}:
        api.post(f"/api/v1/rebuild/stream/jobs/{job_id}/transitions", {"action": "start"})
        api.post(f"/api/v1/rebuild/stream/jobs/{job_id}/transitions", {"action": "activate"})
    elif state == "PAUSED":
        api.post(f"/api/v1/rebuild/stream/jobs/{job_id}/transitions", {"action": "resume"})
    elif state in {"STARTING", "RECOVERING"}:
        api.post(f"/api/v1/rebuild/stream/jobs/{job_id}/transitions", {"action": "activate"})
    elif state != "RUNNING":
        raise RuntimeError(f"unsupported stream job state: {state}")
    now = datetime.now(timezone.utc)
    events = [
        {"event_id": f"demo-order-{index}", "event_time": (now + timedelta(milliseconds=index * 100)).isoformat(), "key": f"user-{index % 3}", "payload": {"order_id": 1000 + index, "user_id": index % 3, "amount": 20 + index, "region": "华东" if index % 2 == 0 else "华南"}}
        for index in range(12)
    ]
    api.post(f"/api/v1/rebuild/stream/jobs/{job_id}/produce", {
        "count": 12,
        "partition_id": "ecommerce-orders",
        "start_offset": 0,
        "event_time": now.isoformat(),
        "payload": {"business": "ecommerce-order", "amount": 88.8, "region": "华东"},
        "schema": {"business": "string", "amount": "number", "region": "string"},
        "aggregate": {"key_field": "region", "value_field": "amount", "window_size": 12},
    })
    api.post(f"/api/v1/rebuild/stream/jobs/{job_id}/fuse", {
        "streams": {
            "orders": [{"order_id": event["payload"]["order_id"], "amount": event["payload"]["amount"]} for event in events[:6]],
            "payments": [{"order_id": event["payload"]["order_id"], "paid": True} for event in events[:6]],
        },
        "key_field": "order_id",
        "event_time": (now + timedelta(seconds=1)).isoformat(),
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18091")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = args.key_file.read_text(encoding="utf-8").strip()
    token_response = requests.post(
        f"{args.base_url.rstrip('/')}/api/v1/rebuild/validation-token",
        headers={"X-Backend-Validation-Key": key, "X-Backend-Validation-Scope": "high-priority-e2e"}, json={}, timeout=30,
    )
    token_response.raise_for_status()
    token = token_response.json()["data"]["token"]
    api = HttpApi(args.base_url, token)
    result = reconcile_demo(api)
    prime_stream_observation(api, result)
    verified = api.get("/api/v1/rebuild/workflows", {"project_id": result["project_id"]})
    result["workflow_count"] = len(verified)
    result["workflow_names"] = sorted(row["name"] for row in verified)
    result["workflow_node_types"] = {}
    for row in verified:
        definition_id = int(row.get("definition_id") or row.get("id"))
        detail = api.get(f"/api/v1/rebuild/workflows/{definition_id}", {"project_id": result["project_id"]})
        nodes = (detail.get("draft") or {}).get("nodes") or []
        result["workflow_node_types"][row["name"]] = sorted(
            str(node.get("node_type") or node.get("type")) for node in nodes
        )
    stream_job = api.get(f"/api/v1/rebuild/stream/jobs/{result['stream_job_id']}")
    result["stream_job_state"] = stream_job["state"]
    observed_at = datetime.now(timezone.utc)
    observation = api.post(f"/api/v1/rebuild/stream/jobs/{result['stream_job_id']}/observe", {
        "from": (observed_at - timedelta(days=1)).isoformat(),
        "to": (observed_at + timedelta(days=1)).isoformat(),
        "limit": 100,
    })
    result["stream_observation"] = observation
    expected = {flow["name"]: sorted(node["type"] for node in flow["nodes"]) for flow in build_blueprints()}
    result["verdict"] = "PASS" if (
        result["workflow_count"] >= 3
        and all(result["workflow_node_types"].get(name) == types for name, types in expected.items())
        and result["stream_job_state"] == "RUNNING"
        and int(observation.get("success_count") or 0) > 0
    ) else "FAIL"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VERDICT: {result['verdict']} project={result['project_id']} workflows={result['workflow_count']} stream_job={result['stream_job_id']}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create current DolphinScheduler DAG samples for the ecommerce project.

The retired rebuild workflow/execution APIs are deliberately not used here.
The Datara gateway selects the project and owner-visible DBX connection;
workflow definition save uses the same signed embed route as the DAG canvas.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import secrets
from pathlib import Path
from typing import Any

import requests

PROJECT_NAME = "电商全域数据治理项目"
SQL_DIR = Path(__file__).resolve().parent / "fixtures" / "business" / "ecom_sim_20261030"
VARIABLES_MODULE = Path(__file__).resolve().parent / "fixtures" / "business" / "import_ecommerce_sim_variables.py"
WORKFLOWS = (
    ("[ECOM-SIM-20261030] 订单支付对账", "ecom_order_payment_reconciliation.sql"),
    ("[ECOM-SIM-20261030] 退款超额核查", "ecom_refund_overpayment_check.sql"),
    ("[ECOM-SIM-20261030] 库存安全核查", "ecom_inventory_safety_check.sql"),
)


def fixture_global_params() -> list[dict[str, str]]:
    """Project the fixture variable plan into workflow-definition globalParams.

    DolphinScheduler resolves ${prop} from the workflow definition's globalParams
    and binds the value as a JDBC parameter, so each prop keeps its fully
    qualified ``<scope>.<name>`` form and can only ever carry a value.
    """
    spec = importlib.util.spec_from_file_location("_ecom_sim_variables", VARIABLES_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"fixture variable module is unavailable: {VARIABLES_MODULE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = json.loads(module.FIXTURE.read_text(encoding="utf-8"))
    return [
        {"prop": f"{row['scope']}.{row['name']}", "direct": "IN", "type": "VARCHAR", "value": str(row["value"])}
        for row in module.variable_definitions(fixture)
    ]


class HttpApi:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"token": token, "Authorization": f"Bearer {token}"})

    @staticmethod
    def _unwrap(response: requests.Response) -> Any:
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code") != 0:
            message = payload.get("msg") if isinstance(payload, dict) else "invalid response"
            raise RuntimeError(f"Datara API error: {message}")
        return payload.get("data")

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._unwrap(self.session.get(self.base_url + path, params=params, timeout=30))

    def post(self, path: str, body: dict[str, Any] | None = None,
             params: dict[str, Any] | None = None) -> Any:
        return self._unwrap(self.session.post(self.base_url + path, json=body, params=params, timeout=30))

    def create_ds_workflow(self, project_code: str, embed_token: str, form: dict[str, str]) -> Any:
        # Do not send the Datara bearer to DolphinScheduler. The short-lived
        # project-scoped embed token is sufficient for this canvas save route.
        response = requests.post(
            f"{self.base_url}/dolphinscheduler/projects/{project_code}/workflow-definition",
            data=form,
            headers={"X-Datara-Embed-Token": embed_token},
            timeout=30,
        )
        return self._unwrap(response)


def sql_workflow_form(name: str, sql: str, connection_id: str, db_type: str,
                      global_params: list[dict[str, str]] | None = None) -> dict[str, str]:
    """Build one native SQL task using DolphinScheduler 3.4.3's form contract."""
    if not name or not sql.strip() or not connection_id or not db_type:
        raise ValueError("workflow name, SQL, DBX connection and type are required")
    task_code = secrets.randbelow(8_000_000_000_000_000) + 1_000_000_000_000_000
    task_params = {
        "type": db_type,
        "datasource": connection_id,
        "sqlSource": "SCRIPT",
        "sql": sql,
        "sqlType": 0,
        "displayRows": 100,
        "sendEmail": False,
        "showType": "TABLE",
        "localParams": [],
        "preStatements": [],
        "postStatements": [],
    }
    task = {
        "code": task_code,
        "name": name,
        "description": "[ECOM-SIM-20261030] 电商业务只读核查",
        "taskType": "SQL",
        "taskParams": json.dumps(task_params, ensure_ascii=False),
        "flag": "YES",
        "taskPriority": "MEDIUM",
        "workerGroup": "default",
        "environmentCode": -1,
        "delayTime": 0,
        "failRetryTimes": 0,
        "failRetryInterval": 1,
        "timeoutFlag": "CLOSE",
        "timeout": 0,
    }
    relation = {
        "name": "",
        "preTaskCode": 0,
        "preTaskVersion": 0,
        "postTaskCode": task_code,
        "postTaskVersion": 0,
        "conditionType": 0,
        "conditionParams": "{}",
    }
    return {
        "name": name,
        "description": "[ECOM-SIM-20261030] 已核对业务 SQL；运行时使用 DBX 连接",
        "globalParams": json.dumps(global_params or [], ensure_ascii=False),
        "locations": json.dumps([{"taskCode": task_code, "x": 80, "y": 160}]),
        "timeout": "0",
        "taskRelationJson": json.dumps([relation]),
        "taskDefinitionJson": json.dumps([task], ensure_ascii=False),
        "executionType": "PARALLEL",
    }


def reconcile_demo(api: HttpApi, *, connection_id: str) -> dict[str, Any]:
    projects_payload = api.get("/api/v1/rebuild/projects")
    projects = projects_payload if isinstance(projects_payload, list) else projects_payload.get("list", [])
    project = next((row for row in projects if row.get("name") == PROJECT_NAME), None)
    if project is None:
        raise RuntimeError(f"Datara project {PROJECT_NAME!r} does not exist")
    project_id = int(project["id"])

    sources = api.get("/api/v1/rebuild/orchestration/datasources", {"project_id": project_id})
    connection = next((row for row in sources if str(row.get("id")) == connection_id), None)
    if connection is None:
        raise RuntimeError(f"DBX connection {connection_id!r} is not visible in project {project_id}")
    db_type = str(connection.get("type") or "")
    if not db_type:
        raise RuntimeError(f"DBX connection {connection_id!r} has no DolphinScheduler type")

    ds_session = api.get("/api/v1/rebuild/orchestration/session", {"project_id": project_id})
    project_code = str(ds_session.get("projectCode") or "")
    embed_token = str(ds_session.get("token") or "")
    if not project_code or not embed_token:
        raise RuntimeError("DolphinScheduler canvas session is unavailable")

    results = []
    global_params = fixture_global_params()
    for name, filename in WORKFLOWS:
        # Search each exact name to remain idempotent even when the project has
        # more than one page of unrelated workflows.
        rows = api.get("/api/v1/rebuild/orchestration/workflow-definitions", {
            "project_id": project_id, "search_val": name, "page_size": 200,
        })
        existing = next((row for row in rows.get("list", []) if row.get("name") == name), None)
        if existing is not None:
            results.append({"name": name, "code": existing["code"], "created": False})
            continue
        sql = (SQL_DIR / filename).read_text(encoding="utf-8")
        form = sql_workflow_form(name, sql, connection_id, db_type, global_params)
        created = api.create_ds_workflow(project_code, embed_token, form)
        if not isinstance(created, dict) or not created.get("code"):
            raise RuntimeError(f"DolphinScheduler did not return a workflow code for {name}")
        results.append({"name": name, "code": created["code"], "created": True})
    for result in results:
        rows = api.get("/api/v1/rebuild/orchestration/workflow-definitions", {
            "project_id": project_id, "search_val": result["name"], "page_size": 200,
        })
        if not any(row.get("name") == result["name"] and str(row.get("code")) == str(result["code"])
                   for row in rows.get("list", [])):
            raise RuntimeError(f"workflow is not visible in Datara task center: {result['name']}")
    return {"project_id": project_id, "project_code": project_code, "workflows": results}


def run_formal_sample(api: HttpApi, result: dict[str, Any]) -> Any:
    """Publish and run the first read-only sample through the current DS gateway."""
    workflow = result["workflows"][0]
    project_id = result["project_id"]
    code = int(workflow["code"])
    api.post(
        f"/api/v1/rebuild/orchestration/workflow-definitions/{code}/release",
        params={"project_id": project_id, "release_state": "ONLINE"},
    )
    return api.post("/api/v1/rebuild/orchestration/workflow-instances/start", {
        "projectId": project_id,
        "workflowDefinitionCode": code,
        "dryRun": False,
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://192.168.1.9:8090")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--connection-id", default="datara-mysql-src")
    parser.add_argument("--run", action="store_true", help="publish and run the first sample in DolphinScheduler")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    key = args.key_file.read_text(encoding="utf-8").strip()
    response = requests.post(
        f"{args.base_url.rstrip('/')}/api/v1/rebuild/validation-token",
        headers={"X-Backend-Validation-Key": key, "X-Backend-Validation-Scope": "high-priority-e2e"},
        json={}, timeout=30,
    )
    token = HttpApi._unwrap(response)["token"]
    api = HttpApi(args.base_url, token)
    result = reconcile_demo(api, connection_id=args.connection_id)
    if args.run:
        result["sample_run"] = run_formal_sample(api, result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

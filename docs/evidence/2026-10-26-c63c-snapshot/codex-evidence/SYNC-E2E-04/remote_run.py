import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASE = "http://172.31.0.8:8001"
OUT = Path("/lei/datara/evidence/SYNC-E2E-04")
PROJECT_NAME = "SYNC-E2E-04 fixture project"
WORKFLOW_NAME = "SYNC-E2E-04 fixture sync"
SOURCE_NAME = "SYNC-E2E-04 ec_retail source"
TARGET_NAME = "SYNC-E2E-04 datara_dw target"


def env_from(container: str, name: str) -> str:
    return subprocess.check_output(
        ["docker", "exec", container, "printenv", name], text=True
    ).strip()


def request(method: str, path: str, *, token: str = "", body=None, extra_headers=None):
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["token"] = token
        headers["Authorization"] = f"Bearer {token}"
    headers.update(extra_headers or {})
    req = urllib.request.Request(
        BASE + path,
        method=method,
        headers=headers,
        data=None if body is None else json.dumps(body).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"raw": raw[:2000].decode("utf-8", errors="replace")}
        return exc.code, payload


def ok(method: str, path: str, *, token: str = "", body=None, expected=(200,), extra_headers=None):
    status, payload = request(
        method, path, token=token, body=body, extra_headers=extra_headers
    )
    if status not in expected or not isinstance(payload, dict) or payload.get("code") != 0:
        raise RuntimeError(f"{method} {path} -> HTTP {status}: {payload}")
    return payload.get("data")


def items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "list", "records"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def component_versions(token: str) -> dict[str, int]:
    status, data = request("GET", "/api/v1/rebuild/components/spec?workflow_type=SYNC", token=token)
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError(f"component spec catalogue -> HTTP {status}")
    found: dict[str, int] = {}

    def walk(value):
        if isinstance(value, dict):
            component_type = value.get("type") or value.get("component_type")
            version = value.get("version", value.get("publishedVersion"))
            if isinstance(component_type, str) and isinstance(version, int):
                found[component_type] = max(found.get(component_type, 0), version)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    return found


def find_or_create_project(token: str) -> tuple[int, bool]:
    projects = items(ok("GET", "/api/v1/rebuild/projects", token=token))
    current = next((item for item in projects if item.get("name") == PROJECT_NAME), None)
    if current:
        return int(current["id"]), False
    created = ok(
        "POST",
        "/api/v1/rebuild/projects",
        token=token,
        body={"name": PROJECT_NAME, "description": "Deterministic INFRA-DATA-01 product API E2E"},
    )
    return int(created["id"]), True


def find_or_create_datasource(token: str, project_id: int, body: dict) -> tuple[int, bool]:
    path = f"/api/v1/rebuild/projects/{project_id}/datasources"
    existing = items(ok("GET", path, token=token))
    current = next((item for item in existing if item.get("name") == body["name"]), None)
    if current:
        return int(current["id"]), False
    created = ok("POST", path, token=token, body=body, expected=(201,))
    return int(created["id"]), True


def find_or_create_workflow(token: str, project_id: int) -> tuple[int, bool]:
    path = f"/api/v1/rebuild/workflows?project_id={project_id}"
    existing = items(ok("GET", path, token=token))
    current = next((item for item in existing if item.get("name") == WORKFLOW_NAME), None)
    if current:
        return int(current["definition_id"]), False
    created = ok(
        "POST",
        "/api/v1/rebuild/workflows",
        token=token,
        body={
            "project_id": project_id,
            "name": WORKFLOW_NAME,
            "description": "ec_retail fixture view to datara_dw fixture actual",
            "workflow_type": "SYNC",
        },
    )
    return int(created["definition_id"]), True


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    result = {
        "ticket": "SYNC-E2E-04",
        "api_base": BASE,
        "token_persisted": False,
        "direct_actual_sql_write": False,
        "legacy_redis_api_used": False,
    }
    token = ""
    try:
        validation_key = env_from("datara-rebuild-api", "REBUILD_VALIDATION_KEY")
        status, issued = request(
            "POST",
            "/api/v1/rebuild/validation-token",
            extra_headers={
                "X-Backend-Validation-Key": validation_key,
                "X-Backend-Validation-Scope": "high-priority-e2e",
            },
        )
        if status != 200 or not isinstance(issued, dict):
            raise RuntimeError(f"validation-token -> HTTP {status}: {issued}")
        token = str((issued.get("data") or {}).get("token") or "")
        if not token:
            raise RuntimeError("validation-token response contained no token")
        result["token_issue_http"] = status

        project_id, project_created = find_or_create_project(token)
        source_password = env_from("datara-mysql-src", "MYSQL_ROOT_PASSWORD")
        target_password = env_from("datara-mysql-dw", "MYSQL_ROOT_PASSWORD")
        source_id, source_created = find_or_create_datasource(
            token,
            project_id,
            {
                "name": SOURCE_NAME,
                "kind": "mysql",
                "host": "datara-mysql-src",
                "port": 3306,
                "database": "ec_retail",
                "username": "root",
                "password": source_password,
                "probe": False,
            },
        )
        target_id, target_created = find_or_create_datasource(
            token,
            project_id,
            {
                "name": TARGET_NAME,
                "kind": "mysql",
                "host": "datara-mysql-dw",
                "port": 3306,
                "database": "datara_dw",
                "username": "root",
                "password": target_password,
                "probe": False,
            },
        )
        source_password = target_password = ""
        source_test = ok(
            "POST", f"/api/v1/rebuild/projects/{project_id}/datasources/{source_id}/test", token=token
        )
        target_test = ok(
            "POST", f"/api/v1/rebuild/projects/{project_id}/datasources/{target_id}/test", token=token
        )

        workflow_id, workflow_created = find_or_create_workflow(token, project_id)
        versions = component_versions(token)
        required = ("endpoint_select", "field_map", "condition_set")
        missing = [name for name in required if versions.get(name, 0) < 1]
        if missing:
            raise RuntimeError(f"published component specs missing: {missing}; discovered={versions}")

        columns = [
            "fixture_key", "item_id", "order_id", "order_no", "user_id",
            "username", "goods_id", "goods_name", "qty", "unit_price",
            "item_amount", "order_status", "pay_channel", "pay_amount", "order_date",
        ]
        mappings = [
            {
                "source_column": name,
                "target_column": name,
                "source_type": "source",
                "target_type": "target",
                "transform_expression": "",
                "nullable": name in {"pay_channel", "pay_amount"},
                "default_value": None,
                "mapping_status": "AUTO",
            }
            for name in columns
        ]
        nodes = [
            {
                "node_code": "endpoint",
                "node_type": "endpoint_select",
                "name": "Fixture endpoints",
                "component_ref": {"type": "endpoint_select", "version": versions["endpoint_select"]},
                "params": {
                    "baseMode": "src_base",
                    "source": {"datasource_id": source_id, "schema": "ec_retail", "object": "fixture_order_detail_source"},
                    "target": {"datasource_id": target_id, "schema": "datara_dw", "object": "fixture_order_detail_actual"},
                    "target_properties": {
                        "primary_key_conflict": {"primary_key": ["item_id"], "conflict_strategy": "insert"},
                        "batch_concurrency": {"batch_size": 100, "concurrency": 1},
                    },
                },
                "position_x": 100,
                "position_y": 100,
            },
            {
                "node_code": "mapping",
                "node_type": "field_map",
                "name": "Fixture identity mapping",
                "component_ref": {"type": "field_map", "version": versions["field_map"]},
                "params": {"inputs": ["endpoint:sourceRef", "endpoint:targetRef"], "mappings": mappings},
                "position_x": 360,
                "position_y": 100,
            },
            {
                "node_code": "condition",
                "node_type": "condition_set",
                "name": "Fixture guard",
                "component_ref": {"type": "condition_set", "version": versions["condition_set"]},
                "params": {"inputs": ["mapping:"], "filterExpr": "fixture_key == 'INFRA-DATA-01'"},
                "position_x": 620,
                "position_y": 100,
            },
        ]
        for node in nodes:
            ok(
                "POST",
                f"/api/v1/rebuild/workflows/{workflow_id}/nodes",
                token=token,
                body={"project_id": project_id, **node},
            )
        for source, target in (("endpoint", "mapping"), ("mapping", "condition")):
            ok(
                "POST",
                f"/api/v1/rebuild/workflows/{workflow_id}/edges",
                token=token,
                body={"project_id": project_id, "from_node": source, "to_node": target},
            )

        graph = ok(
            "GET", f"/api/v1/rebuild/workflows/{workflow_id}?project_id={project_id}", token=token
        )
        snapshot = ok(
            "POST",
            f"/api/v1/rebuild/trial/definitions/{workflow_id}/snapshot",
            token=token,
            body={"project_id": project_id},
        )
        snapshot_id = int(snapshot["snapshot_id"])
        trial = ok(
            "POST",
            f"/api/v1/rebuild/trial/definitions/{workflow_id}/run",
            token=token,
            body={"project_id": project_id, "snapshot_id": snapshot_id, "options": {}},
        )
        instance_id = int(trial["instance_id"])
        trial_detail = ok(
            "GET", f"/api/v1/rebuild/trial/runs/{instance_id}?project_id={project_id}", token=token
        )
        run_stats = ok(
            "GET",
            f"/api/v1/rebuild/execution/run-stats?project_id={project_id}&workflow_instance_id={instance_id}",
            token=token,
        )
        attempt_info = ok(
            "GET",
            f"/api/v1/rebuild/execution/workflow-instances/{instance_id}/attempts?project_id={project_id}",
            token=token,
        )

        verify = subprocess.run(
            ["bash", "/lei/datara/infra/fixtures/business/verify.sh", "synced"],
            cwd="/lei/datara",
            text=True,
            capture_output=True,
            check=False,
        )
        stat_items = items(run_stats)
        result.update(
            {
                "project": {"id": project_id, "created": project_created},
                "datasources": {
                    "source": {"id": source_id, "created": source_created, "test": source_test},
                    "target": {"id": target_id, "created": target_created, "test": target_test},
                },
                "workflow": {
                    "id": workflow_id,
                    "created": workflow_created,
                    "type": graph.get("workflow_type"),
                    "node_types": [node.get("node_type") for node in (graph.get("draft") or {}).get("nodes", [])],
                    "edge_count": len((graph.get("draft") or {}).get("edges", [])),
                },
                "component_versions": {name: versions[name] for name in required},
                "snapshot_id": snapshot_id,
                "instance_id": instance_id,
                "trial": trial,
                "trial_detail": trial_detail,
                "attempts": attempt_info,
                "run_stats": stat_items,
                "verify_synced": {"exit_code": verify.returncode, "stdout": verify.stdout.strip(), "stderr": verify.stderr.strip()},
            }
        )
        workflow_stat = stat_items[0] if stat_items else {}
        trial_stats = trial_detail.get("stats") if isinstance(trial_detail, dict) else {}
        result["acceptance"] = {
            "trial_succeeded": trial.get("status") == "SUCCEEDED",
            "target_matches_expected": verify.returncode == 0,
            "workflow_success_4_failure_0": workflow_stat.get("success_count") == 4 and workflow_stat.get("failure_count") == 0,
            "trial_stats_success_4_failure_0": isinstance(trial_stats, dict) and trial_stats.get("success_count") == 4 and trial_stats.get("failed_count") == 0,
        }
        result["status"] = "PASS" if all(result["acceptance"].values()) else "FAIL"
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if token:
            logout_status, logout_body = request("POST", "/api/v1/rebuild/logout", token=token)
            result["logout"] = {"http": logout_status, "code": logout_body.get("code") if isinstance(logout_body, dict) else None}
        result_path = OUT / "result.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result_path.chmod(0o600)

    print(f"STATUS={result.get('status')}")
    print(f"PROJECT={result.get('project', {}).get('id', 'n/a')} WORKFLOW={result.get('workflow', {}).get('id', 'n/a')} INSTANCE={result.get('instance_id', 'n/a')}")
    print(f"ACCEPTANCE={json.dumps(result.get('acceptance', {}), sort_keys=True)}")
    print(f"LOGOUT={result.get('logout')}")
    if result.get("error"):
        print(f"ERROR={result['error']}")
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

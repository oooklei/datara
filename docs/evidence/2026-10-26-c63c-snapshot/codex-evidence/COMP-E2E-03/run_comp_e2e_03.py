import json
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests


BASE = "http://127.0.0.1:18091"
PROJECT_ID = 26
ENVIRONMENT_GROUP_ID = 303


def validation_key():
    lines = subprocess.check_output(
        ["docker", "inspect", "datara-rebuild-api", "--format", "{{range .Config.Env}}{{println .}}{{end}}"],
        text=True,
    ).splitlines()
    for line in lines:
        if line.startswith("REBUILD_VALIDATION_KEY="):
            return line.split("=", 1)[1]
    raise AssertionError("REBUILD_VALIDATION_KEY missing from API container")


class Api:
    def __init__(self, token):
        self.token = token
        self.headers = {"Authorization": "Bearer " + token}

    def call(self, method, path, *, body=None, files=None, expected=(200,)):
        response = requests.request(
            method,
            BASE + path,
            headers=self.headers,
            json=body if files is None else None,
            files=files,
            timeout=30,
        )
        if response.status_code not in expected:
            raise AssertionError(f"{method} {path}: HTTP {response.status_code} {response.text[:500]}")
        payload = response.json()
        if response.status_code < 300 and "code" in payload and payload.get("code") != 0:
            raise AssertionError(f"{method} {path}: envelope={payload}")
        return payload

    def get(self, path):
        return self.call("GET", path)

    def post(self, path, body):
        return self.call("POST", path, body=body)


def query_outputs(instance_id):
    code = f'''import json, os
from sqlalchemy import create_engine, text
engine = create_engine(os.environ["REBUILD_DB_URL"])
with engine.connect() as connection:
    rows = connection.execute(text("SELECT ti.task_id, tio.output_json FROM task_instance_output tio JOIN task_instance ti ON ti.id=tio.task_instance_id WHERE ti.workflow_instance_id=:iid ORDER BY tio.id"), {{"iid": {int(instance_id)}}}).fetchall()
print(json.dumps([{{"task_id": row[0], "output": json.loads(row[1])}} for row in rows]))
'''
    raw = subprocess.check_output(
        ["docker", "exec", "datara-rebuild-api", "python", "-c", code], text=True
    )
    return json.loads(raw)


def save_variable(api, marker, scope, value, **extra):
    body = {
        "scope": scope,
        "name": marker,
        "value_type": "string",
        "value": value,
        **extra,
    }
    saved = api.post(f"/api/v1/rebuild/variables?project_id={PROJECT_ID}", body)["data"]
    assert saved["saved"] is True


def delete_variable(api, marker, scope, **query):
    params = {"project_id": PROJECT_ID, "scope": scope, **query}
    api.call("DELETE", f"/api/v1/rebuild/variables/{marker}?{urlencode(params)}")


def completion_value(api, marker, context):
    rows = api.post(
        "/api/v1/rebuild/variables/complete",
        {"prefix": marker, "context": context},
    )["data"]
    matches = [row for row in rows if row["name"] == marker]
    assert len(matches) == 1, matches
    return {"scope": matches[0]["scope"], "value": matches[0]["current_value"]}


def main():
    issued = requests.post(
        BASE + "/api/v1/rebuild/validation-token",
        headers={
            "X-Backend-Validation-Key": validation_key(),
            "X-Backend-Validation-Scope": "high-priority-e2e",
        },
        timeout=20,
    )
    issued.raise_for_status()
    token_data = issued.json()["data"]
    assert token_data["expires_in"] == 900
    api = Api(token_data["token"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    marker = "c3_" + stamp[-6:]
    cleanup = []
    report = {
        "ticket": "COMP-E2E-03",
        "base": "http://192.168.1.9:18091",
        "validation_token": {"issued": True, "expires_in": token_data["expires_in"], "persisted": False},
        "reused": {"project_id": PROJECT_ID, "source_workflow_id": 25},
    }
    try:
        health = requests.get(BASE + "/api/v1/rebuild/health", timeout=20).json()
        assert health["code"] == 0
        report["health"] = "ok"

        source_workflow = api.get(f"/api/v1/rebuild/workflows/25?project_id={PROJECT_ID}")["data"]
        assert source_workflow["definition_id"] == 25
        refs = {
            node["node_type"]: node["params"]["resourceRef"]
            for node in source_workflow["draft"]["nodes"]
            if node["node_type"] in {"sql", "python", "shell"}
        }
        assert set(refs) == {"sql", "python", "shell"}
        assert all(ref["version"] == 1 for ref in refs.values())

        specs = api.get("/api/v1/rebuild/components/spec?workflow_type=NORMAL")["items"]
        component_versions = {
            row["type"]: row["publishedVersion"]
            for row in specs
            if row["type"] in {"sql", "python", "shell", "dependent"}
        }
        assert set(component_versions) == {"sql", "python", "shell", "dependent"}

        resource_versions = {}
        for kind, ref in refs.items():
            detail = api.get(
                f"/api/v1/rebuild/resources/{ref['resourceId']}/versions/{ref['version']}?project_id={PROJECT_ID}"
            )["data"]
            assert detail["version"] == 1
            resource_versions[kind] = {
                "resource_id": ref["resourceId"],
                "version": detail["version"],
                "digest": detail.get("digest") or detail.get("sha256"),
                "size_bytes": detail["size_bytes"],
            }
        report["resource_versions"] = resource_versions

        created = api.post(
            "/api/v1/rebuild/workflows",
            {
                "project_id": PROJECT_ID,
                "name": "COMP-E2E-03-" + stamp,
                "description": "isolated component-chain acceptance",
                "workflow_type": "NORMAL",
            },
        )["data"]
        workflow_id = int(created["definition_id"])
        report["isolated_workflow_id"] = workflow_id

        dependency = api.post(
            "/api/v1/rebuild/dependency/saves",
            {
                "project_id": PROJECT_ID,
                "workflow_id": workflow_id,
                "workflow_version": 1,
                "task_id": "dependency_gate",
                "groups": [{
                    "join": "AND",
                    "conditions": [{
                        "kind": "workflow",
                        "upstream_workflow_id": workflow_id,
                        "upstream_workflow_version": 1,
                        "upstream_task_code": 0,
                        "selector": "workflow",
                        "cycle": "day",
                        "date_value": "last1Days",
                        "depend_result": "success",
                        "parameter_passing": False,
                    }],
                }],
            },
        )["data"]
        dependency_id = int(dependency["config_id"])
        report["dependency_id"] = dependency_id

        save_variable(api, marker, "global", "global-value")
        cleanup.append(("global", {}))
        save_variable(
            api, marker, "env", "env-value", environment_group_id=ENVIRONMENT_GROUP_ID
        )
        cleanup.append(("env", {"environment_group_id": ENVIRONMENT_GROUP_ID}))
        save_variable(api, marker, "workflow", "workflow-value", workflow_id=workflow_id)
        cleanup.append(("workflow", {"workflow_id": workflow_id}))
        save_variable(api, marker, "task", "node-value", task_id="variable_probe")
        cleanup.append(("task", {"task_id": "variable_probe"}))

        precedence = {
            "node": completion_value(api, marker, {
                "project_id": PROJECT_ID,
                "workflow_id": workflow_id,
                "task_id": "variable_probe",
                "environment_group_id": ENVIRONMENT_GROUP_ID,
            }),
            "workflow": completion_value(api, marker, {
                "project_id": PROJECT_ID,
                "workflow_id": workflow_id,
                "environment_group_id": ENVIRONMENT_GROUP_ID,
            }),
            "environment_group": completion_value(api, marker, {
                "project_id": PROJECT_ID,
                "environment_group_id": ENVIRONMENT_GROUP_ID,
            }),
            "global": completion_value(api, marker, {"project_id": PROJECT_ID}),
        }
        assert precedence == {
            "node": {"scope": "task", "value": "node-value"},
            "workflow": {"scope": "workflow", "value": "workflow-value"},
            "environment_group": {"scope": "env", "value": "env-value"},
            "global": {"scope": "global", "value": "global-value"},
        }
        report["variable_precedence"] = precedence

        probe_script = (
            f'print("NODE=${{task.{marker}}}|WORKFLOW=${{workflow.{marker}}}'
            f'|ENV=${{env.{marker}}}|GLOBAL=${{global.{marker}}}")'
        )
        nodes = [
            ("sql_resource", "sql", {"sourceMode": "resource", "resourceRef": refs["sql"], "execute": True}),
            ("python_resource", "python", {"sourceMode": "resource", "resourceRef": refs["python"]}),
            ("shell_resource", "shell", {"sourceMode": "resource", "resourceRef": refs["shell"]}),
            ("variable_probe", "python", {"script": probe_script}),
            ("dependency_gate", "dependent", {"dependency_id": dependency_id}),
        ]
        for node_code, node_type, params in nodes:
            api.post(
                f"/api/v1/rebuild/workflows/{workflow_id}/nodes",
                {
                    "project_id": PROJECT_ID,
                    "node_code": node_code,
                    "node_type": node_type,
                    "component_ref": {"type": node_type, "version": component_versions[node_type]},
                    "params": params,
                },
            )
        for left, right in zip(nodes, nodes[1:]):
            api.post(
                f"/api/v1/rebuild/workflows/{workflow_id}/edges",
                {"project_id": PROJECT_ID, "from_node": left[0], "to_node": right[0]},
            )

        bindings = {}
        for kind, task_id in (("sql", "sql_resource"), ("python", "python_resource"), ("shell", "shell_resource")):
            bound = api.post(
                "/api/v1/rebuild/resources/bindings",
                {
                    "project_id": PROJECT_ID,
                    "workflow_id": workflow_id,
                    "workflow_version": 1,
                    "task_id": task_id,
                    "resource_id": refs[kind]["resourceId"],
                    "resource_version": refs[kind]["version"],
                },
            )["data"]
            assert bound["bound"] is True
            bindings[kind] = bound["binding_id"]
        report["resource_bindings"] = bindings

        snap_created = api.post(
            f"/api/v1/rebuild/trial/definitions/{workflow_id}/snapshot",
            {"project_id": PROJECT_ID},
        )["data"]
        snapshot_id = int(snap_created["snapshot_id"])
        snapshot = api.get(
            f"/api/v1/rebuild/trial/snapshots/{snapshot_id}?project_id={PROJECT_ID}"
        )["data"]
        snapshot_nodes = {node["node_code"]: node for node in snapshot["node_snapshot_json"]}
        for kind, task_id in (("sql", "sql_resource"), ("python", "python_resource"), ("shell", "shell_resource")):
            assert snapshot_nodes[task_id]["params"]["resourceRef"] == refs[kind]
        report["snapshot"] = {
            "snapshot_id": snapshot_id,
            "digest": snapshot["snapshot_digest"],
            "node_count": len(snapshot_nodes),
            "resource_refs_pinned": True,
        }

        run_results = {}
        expected_probe = "NODE=node-value|WORKFLOW=workflow-value|ENV=env-value|GLOBAL=global-value"
        for label, mock_status, expected_status, expected_counts in (
            ("success", "SUCCEEDED", "SUCCEEDED", (5, 0)),
            ("failure", "FAILED", "FAILED", (4, 1)),
        ):
            run = api.post(
                f"/api/v1/rebuild/trial/definitions/{workflow_id}/run",
                {
                    "project_id": PROJECT_ID,
                    "snapshot_id": snapshot_id,
                    "options": {
                        "environment_group_id": ENVIRONMENT_GROUP_ID,
                        "dependency_mock": {str(dependency_id): mock_status},
                    },
                },
            )["data"]
            instance_id = int(run["instance_id"])
            assert run["status"] == expected_status
            assert run["task_count"] == 5
            task_statuses = {task["task_id"]: task["status"] for task in run["tasks"]}
            assert task_statuses["dependency_gate"] == expected_status
            assert all(task_statuses[name] == "SUCCEEDED" for name in (
                "sql_resource", "python_resource", "shell_resource", "variable_probe"
            ))

            instance = api.get(
                f"/api/v1/rebuild/execution/workflow-instances/{instance_id}?project_id={PROJECT_ID}"
            )["data"]
            assert instance["status"] == expected_status
            assert instance["trial_snapshot_id"] == snapshot_id

            aggregate = api.get(
                f"/api/v1/rebuild/trial/runs/{instance_id}?project_id={PROJECT_ID}"
            )["data"]
            assert aggregate["status"] == expected_status and aggregate["found"] is True
            all_logs = [entry["message"] for group in aggregate["logs"] for entry in group["logs"]]
            assert any(f"mock={mock_status}" in message for message in all_logs)

            runtime_snapshot = api.get(
                f"/api/v1/rebuild/variables/run-snapshot?instance_id={instance_id}&project_id={PROJECT_ID}"
            )["data"]
            marker_rows = [row for row in runtime_snapshot if row["name"] == marker]
            assert marker_rows and marker_rows[-1]["resolved_value"] == "node-value"
            assert marker_rows[-1]["source"] == "task." + marker

            stats_items = api.get(
                f"/api/v1/rebuild/execution/run-stats?project_id={PROJECT_ID}&workflow_instance_id={instance_id}"
            )["data"]["items"]
            assert len(stats_items) == 1
            stat = stats_items[0]
            assert (stat["success_count"], stat["failure_count"]) == expected_counts
            assert stat["status"] == expected_status

            outputs = query_outputs(instance_id)
            by_task = {row["task_id"]: row["output"] for row in outputs}
            assert by_task["sql_resource"]["row_count"] >= 1
            assert by_task["python_resource"]["exit_code"] == 0 and by_task["python_resource"]["stdout"]
            assert by_task["shell_resource"]["exit_code"] == 0 and by_task["shell_resource"]["stdout"]
            assert by_task["variable_probe"]["exit_code"] == 0
            assert expected_probe in by_task["variable_probe"]["stdout"]

            run_results[label] = {
                "instance_id": instance_id,
                "status": instance["status"],
                "task_statuses": task_statuses,
                "output_checks": {
                    "sql_row_count": by_task["sql_resource"]["row_count"],
                    "python_stdout": by_task["python_resource"]["stdout"].strip(),
                    "shell_stdout": by_task["shell_resource"]["stdout"].strip(),
                    "variable_probe_stdout": by_task["variable_probe"]["stdout"].strip(),
                },
                "runtime_snapshot": marker_rows[-1],
                "run_stats": {
                    "success_count": stat["success_count"],
                    "failure_count": stat["failure_count"],
                    "skipped_count": stat["skipped_count"],
                    "total_count": stat["total_count"],
                },
                "dependency_log_verified": True,
            }
        report["runs"] = run_results
        report["result"] = "PASS"
    finally:
        cleanup_errors = []
        for scope, query in reversed(cleanup):
            try:
                delete_variable(api, marker, scope, **query)
            except Exception as exc:
                cleanup_errors.append(f"{scope}: {exc}")
        report["variable_cleanup"] = {"deleted": len(cleanup) - len(cleanup_errors), "errors": cleanup_errors}
        logout = requests.post(BASE + "/api/v1/rebuild/logout", headers=api.headers, timeout=20)
        report["logout"] = logout.status_code == 200 and logout.json().get("code") == 0
        revoked = requests.get(
            BASE + f"/api/v1/rebuild/workflows?project_id={PROJECT_ID}", headers=api.headers, timeout=20
        )
        report["token_revoked"] = revoked.status_code == 401
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

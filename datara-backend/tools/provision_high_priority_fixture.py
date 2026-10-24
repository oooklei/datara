"""Provision a bounded workflow/stream fixture for the 1.9 acceptance run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json

from tools.high_priority_e2e import call


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--project-id", required=True, type=int)
    args = parser.parse_args()

    login = call(
        args.base,
        "/api/v1/rebuild/login",
        method="POST",
        body={"username": args.username, "password": args.password},
    )
    token = login["data"]["token"]
    specs = call(args.base, "/api/v1/rebuild/components/spec?workflow_type=NORMAL", token=token)
    versions = {item["type"]: item["publishedVersion"] for item in specs.get("items", [])}
    required = {"sql", "python", "shell", "dependent"}
    if not required <= versions.keys():
        raise RuntimeError(f"NORMAL component catalogue is incomplete: {sorted(required - versions.keys())}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    created = call(
        args.base,
        "/api/v1/rebuild/workflows",
        token=token,
        method="POST",
        body={
            "project_id": args.project_id,
            "name": f"high-priority-e2e-{stamp}",
            "workflow_type": "NORMAL",
        },
    )
    definition_id = int(created["data"]["definition_id"])
    dependency = call(
        args.base,
        "/api/v1/rebuild/dependency/saves",
        token=token,
        method="POST",
        body={
            "project_id": args.project_id,
            "workflow_id": definition_id,
            "workflow_version": 1,
            "task_id": "dependency_1",
            "groups": [{
                "join": "AND",
                "conditions": [{
                    "kind": "workflow",
                    "upstream_workflow_id": definition_id,
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
    )
    dependency_id = int(dependency["data"]["config_id"])
    nodes = (
        ("sql_1", "sql", {"sql": "SELECT 1 AS value", "execute": True}),
        ("python_1", "python", {"script": "print('python-ok')"}),
        ("shell_1", "shell", {"script": "printf shell-ok"}),
        ("dependency_1", "dependent", {"dependency_id": dependency_id}),
        ("sql_2", "sql", {"sql": "SELECT 2 AS value", "execute": True}),
        ("shell_2", "shell", {"script": "printf complete"}),
    )
    for node_code, component_type, params in nodes:
        call(
            args.base,
            f"/api/v1/rebuild/workflows/{definition_id}/nodes",
            token=token,
            method="POST",
            body={
                "project_id": args.project_id,
                "node_code": node_code,
                "node_type": component_type,
                "component_ref": {"type": component_type, "version": versions[component_type]},
                "params": params,
            },
        )
    for (source, *_), (target, *__) in zip(nodes, nodes[1:]):
        call(
            args.base,
            f"/api/v1/rebuild/workflows/{definition_id}/edges",
            token=token,
            method="POST",
            body={"project_id": args.project_id, "from_node": source, "to_node": target},
        )
    snapshot = call(
        args.base,
        f"/api/v1/rebuild/trial/definitions/{definition_id}/snapshot",
        token=token,
        method="POST",
        body={"project_id": args.project_id},
    )
    stream = call(
        args.base,
        "/api/v1/rebuild/stream/jobs",
        token=token,
        method="POST",
        body={
            "name": f"high-priority-stream-{stamp}",
            "workflow_id": definition_id,
            "mq_topic": f"datara.e2e.{stamp}",
            "runtime_config": {"mode": "fixed_rate", "rows_per_sec": 10, "columns": ["id", "value"]},
        },
    )
    print(json.dumps({
        "project_id": args.project_id,
        "definition_id": definition_id,
        "snapshot_id": int(snapshot["data"]["snapshot_id"]),
        "stream_job_id": int(stream["data"]["id"]),
        "dependency_id": dependency_id,
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

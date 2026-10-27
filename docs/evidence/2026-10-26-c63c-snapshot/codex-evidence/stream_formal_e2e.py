import json
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


base, token_path, evidence_path = sys.argv[1:4]
token = open(token_path, encoding="utf-8").read().strip()


def call(path, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    request = Request(
        base + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    if payload.get("code") != 0:
        raise RuntimeError({"path": path, "payload": payload})
    return payload.get("data")


stamp = time.strftime("%Y%m%d%H%M%S")
report = {"ticket": "STREAM-E2E-02", "base": base}
try:
    project = call(
        "/api/v1/rebuild/projects",
        "POST",
        {"name": f"stream-formal-e2e-{stamp}"},
    )
    project_id = int(project["id"])
    workflow = call(
        "/api/v1/rebuild/workflows",
        "POST",
        {
            "project_id": project_id,
            "name": f"stream-produce-aggregate-fuse-{stamp}",
            "workflow_type": "STREAM",
        },
    )
    workflow_id = int(workflow["definition_id"])
    job = call(
        "/api/v1/rebuild/stream/jobs",
        "POST",
        {
            "name": f"stream-formal-job-{stamp}",
            "workflow_id": workflow_id,
            "mq_topic": f"datara.formal.stream.{stamp}",
            "runtime_config": {
                "mode": "fixed_rate",
                "rows_per_sec": 10,
                "columns": ["id", "value"],
            },
        },
    )
    job_id = int(job["id"])
    call(f"/api/v1/rebuild/stream/jobs/{job_id}/transitions", "POST", {"action": "start"})
    call(f"/api/v1/rebuild/stream/jobs/{job_id}/transitions", "POST", {"action": "activate"})
    produced = call(
        f"/api/v1/rebuild/stream/jobs/{job_id}/produce",
        "POST",
        {
            "count": 5,
            "partition_id": "formal-p0",
            "payload": {"id": "tenant-a", "value": 3},
            "schema": {"id": "string", "value": "integer"},
            "aggregate": {
                "key_field": "id",
                "value_field": "value",
                "window_size": 5,
            },
        },
    )
    fused = call(
        f"/api/v1/rebuild/stream/jobs/{job_id}/fuse",
        "POST",
        {
            "key_field": "id",
            "streams": {
                "orders": [
                    {"id": "tenant-a", "orders": 5},
                    {"id": "tenant-b", "orders": 2},
                ],
                "payments": [
                    {"id": "tenant-a", "paid": 5},
                    {"id": "tenant-b", "paid": 2},
                ],
            },
        },
    )
    window = {"from": "2000-01-01T00:00:00Z", "to": "2100-01-01T00:00:00Z", "limit": 100}
    observed = call(f"/api/v1/rebuild/stream/jobs/{job_id}/observe", "POST", window)
    metrics = call(
        f"/api/v1/rebuild/stream/jobs/{job_id}/metrics?"
        + urlencode({"from": window["from"], "to": window["to"], "limit": 100})
    )
    aggregate = produced.get("metric", {}).get("window_result", {}).get("aggregate")
    if (
        produced.get("produced") != 5
        or not aggregate
        or aggregate[0].get("count") != 5
        or aggregate[0].get("sum") != 15.0
    ):
        raise RuntimeError({"invalid_produce_or_aggregate": produced})
    if fused.get("fused") != 2 or len(fused.get("result", [])) != 2:
        raise RuntimeError({"invalid_fusion": fused})
    metric_items = metrics if isinstance(metrics, list) else metrics.get("items", [])
    if len(metric_items) < 2:
        raise RuntimeError({"missing_metrics": metrics})
    if (
        observed.get("state") != "RUNNING"
        or observed.get("snapshot_count") != 2
        or observed.get("input_count") != 4
        or observed.get("output_count") != 2
        or observed.get("success_count") != 2
        or observed.get("failure_count") != 0
    ):
        raise RuntimeError({"invalid_observation": observed})
    report.update(
        {
            "status": "PASS",
            "project_id": project_id,
            "workflow_id": workflow_id,
            "job_id": job_id,
            "produced": produced["produced"],
            "aggregate_windows": len(aggregate),
            "aggregate_count": aggregate[0]["count"],
            "aggregate_sum": aggregate[0]["sum"],
            "fused": fused["fused"],
            "metric_points": len(metric_items),
            "observe_snapshots": observed["snapshot_count"],
            "observe": observed,
        }
    )
finally:
    try:
        call("/api/v1/rebuild/logout", "POST", {})
        report["logout"] = True
    except Exception as exc:
        report["logout_error"] = str(exc)
    with open(evidence_path, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({key: report.get(key) for key in (
        "ticket", "status", "project_id", "workflow_id", "job_id", "produced",
        "aggregate_windows", "aggregate_count", "aggregate_sum", "fused",
        "metric_points", "observe_snapshots", "logout", "logout_error"
    )}, ensure_ascii=False, separators=(",", ":")))

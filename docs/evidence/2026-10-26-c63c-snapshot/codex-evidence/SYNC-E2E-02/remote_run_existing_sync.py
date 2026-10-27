import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

REBUILD = "http://172.31.0.8:8001"
LEGACY = "http://127.0.0.1:8000"
OUT = Path("/lei/datara/evidence/sync-e2e-02")


def call(method, base, path, token, body=None):
    req = urllib.request.Request(
        base + path,
        method=method,
        headers={"token": token, "Content-Type": "application/json"},
        data=None if body is None else json.dumps(body).encode(),
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"raw": raw[:1000].decode(errors="replace")}
        return exc.code, payload


key = subprocess.check_output(
    ["docker", "exec", "datara-rebuild-api", "printenv", "REBUILD_VALIDATION_KEY"], text=True
).strip()
req = urllib.request.Request(
    REBUILD + "/api/v1/rebuild/validation-token",
    method="POST",
    headers={"X-Backend-Validation-Key": key, "X-Backend-Validation-Scope": "high-priority-e2e"},
)
with urllib.request.urlopen(req, timeout=20) as response:
    token_response = json.loads(response.read())
token = token_response["data"]["token"]
run_status, run_payload = call(
    "POST", LEGACY, "/api/v1/workflow-definitions/wf_8182a5d0/run", token, {"run_mode": "trial"}
)
instance_id = (run_payload.get("data") or {}).get("instanceId") or (run_payload.get("data") or {}).get("instance_id")
polls = []
if instance_id:
    for _ in range(60):
        detail_status, detail_payload = call("GET", LEGACY, f"/api/v1/instances/{instance_id}", token)
        state = str((detail_payload.get("data") or {}).get("state") or (detail_payload.get("data") or {}).get("status") or "")
        polls.append({"http": detail_status, "state": state})
        if state.upper() in {"SUCCEEDED", "FAILED", "STOPPED", "CANCELLED"}:
            break
        time.sleep(2)
    metrics = call("GET", LEGACY, f"/api/v1/instances/{instance_id}/metrics", token)
    events = call("GET", LEGACY, f"/api/v1/instances/{instance_id}/events", token)
else:
    detail_status, detail_payload, metrics, events = 0, {}, [0, {}], [0, {}]
result = {
    "workflow_id": "wf_8182a5d0",
    "token_status": 200,
    "run": [run_status, run_payload],
    "instance_id": instance_id,
    "polls": polls,
    "detail": [detail_status, detail_payload],
    "metrics": metrics,
    "events": events,
    "token_persisted": False,
}
(OUT / "run-existing-sync.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("RUN_HTTP", run_status, "INSTANCE", instance_id or "NONE")
print("FINAL", polls[-1]["state"] if polls else "NO_INSTANCE", "POLLS", len(polls))
print("TOKEN_PERSISTED", False)

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://172.31.0.8:8001"
OUT = Path("/lei/datara/evidence/sync-e2e-02")
OUT.mkdir(parents=True, exist_ok=True)


def call(method, path, token=None, body=None, headers=None):
    request_headers = {"Content-Type": "application/json"}
    if token:
        request_headers["token"] = token
    request_headers.update(headers or {})
    req = urllib.request.Request(
        BASE + path,
        method=method,
        headers=request_headers,
        data=None if body is None else json.dumps(body).encode(),
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


key = subprocess.check_output(
    ["docker", "exec", "datara-rebuild-api", "printenv", "REBUILD_VALIDATION_KEY"], text=True
).strip()
status, issued = call(
    "POST",
    "/api/v1/rebuild/validation-token",
    headers={"X-Backend-Validation-Key": key, "X-Backend-Validation-Scope": "high-priority-e2e"},
)
token = issued["data"]["token"]
result = {"token_status": status}
for name, path in {
    "projects": "/api/v1/rebuild/projects",
    "workflows": "/api/v1/rebuild/workflows?project_id=26",
    "datasources": "/api/v1/rebuild/projects/26/datasources",
}.items():
    result[name] = call("GET", path, token=token)
(OUT / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("TOKEN_ISSUED", status)
print("PROBE_WRITTEN", OUT / "probe.json")
print("TOKEN_PERSISTED", False)

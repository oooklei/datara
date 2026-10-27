import json
import subprocess
import urllib.error
import urllib.request


def request(url, token=None, key=None, scope=None):
    headers = {}
    if token:
        headers["token"] = token
    if key:
        headers["X-Backend-Validation-Key"] = key
        headers["X-Backend-Validation-Scope"] = scope or "high-priority-e2e"
    req = urllib.request.Request(url, method="POST" if key else "GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read()
            return response.status, response.headers.get("content-type"), body[:500].decode(errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return exc.code, exc.headers.get("content-type"), body[:500].decode(errors="replace")


key = subprocess.check_output(
    ["docker", "exec", "datara-rebuild-api", "printenv", "REBUILD_VALIDATION_KEY"], text=True
).strip()
status, _, body = request(
    "http://172.31.0.8:8001/api/v1/rebuild/validation-token", key=key, scope="high-priority-e2e"
)
token = json.loads(body)["data"]["token"]
result = {
    "issued": status,
    "gateway": request("http://127.0.0.1:18091/api/v1/workflow-definitions", token=token),
    "legacy": request("http://127.0.0.1:8000/api/v1/workflow-definitions", token=token),
    "token_persisted": False,
}
with open("/lei/datara/evidence/sync-e2e-02/legacy-probe.json", "w", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
print("ISSUED", status, "GATEWAY", result["gateway"][0], "LEGACY", result["legacy"][0])
print("TOKEN_PERSISTED", False)

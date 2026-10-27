import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request


def call(method, url, token, body=None):
    req = urllib.request.Request(
        url,
        method=method,
        headers={"token": token, "Content-Type": "application/json"},
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
req = urllib.request.Request(
    "http://172.31.0.8:8001/api/v1/rebuild/validation-token",
    method="POST",
    headers={"X-Backend-Validation-Key": key, "X-Backend-Validation-Scope": "high-priority-e2e"},
)
with urllib.request.urlopen(req, timeout=20) as response:
    token = json.loads(response.read())["data"]["token"]
base = "http://127.0.0.1:8000"
results = {}
for term in ("sync", "同步"):
    status, payload = call(
        "GET", base + "/api/v1/workflow-definitions?search=" + urllib.parse.quote(term) + "&page_size=50", token
    )
    results[term] = [status, payload]
details = {}
rows = []
for _, payload in results.values():
    rows.extend(payload.get("data", {}).get("list", []))
for row in rows[:10]:
    details[row["id"]] = call("GET", base + "/api/v1/workflow-definitions/" + row["id"], token)
with open("/lei/datara/evidence/sync-e2e-02/existing-sync.json", "w", encoding="utf-8") as stream:
    json.dump({"searches": results, "details": details, "token_persisted": False}, stream, ensure_ascii=False, indent=2)
print("SYNC_MATCHES", len(rows), "DETAILS", len(details))
print("TOKEN_PERSISTED", False)

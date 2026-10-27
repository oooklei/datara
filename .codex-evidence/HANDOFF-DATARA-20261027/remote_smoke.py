import json
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:18091/api/v1/rebuild"


def request(method: str, path: str, *, headers=None, body=None):
    payload = None if body is None else json.dumps(body).encode()
    req = Request(BASE + path, data=payload, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urlopen(req, timeout=15) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


accounts = {
    "admin": "Admin@123",
    "dev": "Dev@123",
    "analyst": "Analyst@123",
    "viewer": "Viewer@123",
}
login_results = {}
for username, password in accounts.items():
    status, envelope = request("POST", "/login", body={"username": username, "password": password})
    data = envelope.get("data") or {}
    login_results[username] = {
        "http": status,
        "role": (data.get("user") or {}).get("role"),
        "token": bool(data.get("token")),
    }

key = Path("/lei/datara/runtime-secrets/rebuild-validation.key").read_text(encoding="utf-8").strip()
status, envelope = request("POST", "/validation-token", headers={
    "X-Backend-Validation-Key": key,
    "X-Backend-Validation-Scope": "high-priority-e2e",
})
token = (envelope.get("data") or {}).get("token", "")
auth = {"Authorization": f"Bearer {token}"}

checks = {}
for name, path in {
    "projects": "/projects",
    "workflows": "/workflows?project_id=35",
    "variables": "/variables?project_id=35&scopes=project",
    "models": "/models",
    "llm_models": "/llm-models",
}.items():
    code, result = request("GET", path, headers=auth)
    data = result.get("data")
    if isinstance(data, list):
        count = len(data)
    elif isinstance(data, dict):
        rows = data.get("list", data.get("items", []))
        count = len(rows) if isinstance(rows, list) else None
    else:
        count = None
    checks[name] = {"http": code, "count": count}

def container_env(name: str) -> dict[str, str]:
    raw = subprocess.check_output(["docker", "inspect", "-f", "{{json .Config.Env}}", name], text=True)
    return dict(item.split("=", 1) for item in json.loads(raw) if "=" in item)


current_env = container_env("datara-rebuild-api")
previous_env = container_env("datara-rebuild-api-pre-secret-rotation-98dc712a")
pre_llm_env = container_env("datara-rebuild-api-pre-llm-rotation-98dc712a")
security = {
    "validation_key_matches_file": current_env.get("REBUILD_VALIDATION_KEY") == key,
    "validation_key_rotated": current_env.get("REBUILD_VALIDATION_KEY") != previous_env.get("REBUILD_VALIDATION_KEY"),
    "token_secret_rotated": current_env.get("REBUILD_TOKEN_SECRET") != previous_env.get("REBUILD_TOKEN_SECRET"),
    "llm_encryption_key_rotated": current_env.get("LLM_ENCRYPTION_KEY") != pre_llm_env.get("LLM_ENCRYPTION_KEY"),
}

print(json.dumps({
    "validation_token": {"http": status, "issued": bool(token)},
    "logins": login_results,
    "api": checks,
    "security": security,
}, ensure_ascii=False, sort_keys=True))

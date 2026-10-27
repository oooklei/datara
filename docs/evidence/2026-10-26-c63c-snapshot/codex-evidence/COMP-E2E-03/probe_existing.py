import json
import subprocess

import requests


BASE = "http://127.0.0.1:18091"


def validation_key():
    env = subprocess.check_output(
        ["docker", "inspect", "datara-rebuild-api", "--format", "{{range .Config.Env}}{{println .}}{{end}}"],
        text=True,
    ).splitlines()
    for line in env:
        if line.startswith("REBUILD_VALIDATION_KEY="):
            return line.split("=", 1)[1]
    raise RuntimeError("validation key missing")


def main():
    response = requests.post(
        BASE + "/api/v1/rebuild/validation-token",
        headers={
            "X-Backend-Validation-Key": validation_key(),
            "X-Backend-Validation-Scope": "high-priority-e2e",
        },
        timeout=20,
    )
    response.raise_for_status()
    token = response.json()["data"]["token"]
    headers = {"Authorization": "Bearer " + token}
    try:
        results = {}
        for name, path in {
            "projects": "/api/v1/rebuild/projects",
            "workflow25_project26": "/api/v1/rebuild/workflows/25?project_id=26",
            "workflows_project26": "/api/v1/rebuild/workflows?project_id=26",
            "resources_sql": "/api/v1/rebuild/resources?project_id=26&kind=sql",
            "resources_python": "/api/v1/rebuild/resources?project_id=26&kind=python",
            "resources_shell": "/api/v1/rebuild/resources?project_id=26&kind=shell",
        }.items():
            item = requests.get(BASE + path, headers=headers, timeout=20)
            results[name] = {"http": item.status_code, "body": item.json()}
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        requests.post(BASE + "/api/v1/rebuild/logout", headers=headers, timeout=20).raise_for_status()


if __name__ == "__main__":
    main()

import http.client
import json
import sys
import time
import uuid

HOST = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1:18098"
BASE = "/api/v1/rebuild"


def call(path, token, method="GET", body=None, content_type="application/json"):
    connection = http.client.HTTPConnection(HOST, timeout=30)
    payload = None if body is None else (json.dumps(body).encode() if content_type == "application/json" else body)
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        headers["Content-Type"] = content_type
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    if response.status >= 400:
        raise RuntimeError(f"{method} {path}: HTTP {response.status} {raw[:300]!r}")
    data = json.loads(raw)
    if "code" not in data:
        return data
    if data.get("code") != 0:
        raise RuntimeError(f"{method} {path}: {data}")
    return data["data"]


def upload(project_id, kind, filename, content, token):
    boundary = "----datara" + uuid.uuid4().hex
    chunks = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"project_id\"\r\n\r\n{project_id}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"kind\"\r\n\r\n{kind}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return call(
        f"{BASE}/resources/uploads",
        token,
        "POST",
        b"".join(chunks),
        f"multipart/form-data; boundary={boundary}",
    )


def main():
    token_path = sys.argv[1]
    token = open(token_path, encoding="utf-8").read().strip()
    stamp = time.strftime("%Y%m%d%H%M%S")
    specs = call(f"{BASE}/components/spec?workflow_type=NORMAL", token)
    versions = {item["type"]: item["publishedVersion"] for item in specs["items"]}
    project = call(f"{BASE}/projects", token, "POST", {"name": f"resource-e2e-{stamp}"})
    project_id = int(project["id"])
    workflow = call(f"{BASE}/workflows", token, "POST", {
        "project_id": project_id, "name": f"resource-chain-{stamp}", "workflow_type": "NORMAL"
    })
    workflow_id = int(workflow["definition_id"])
    fixtures = (
        ("sql_task", "sql", "bound.sql", b"select 17 as resource_value"),
        ("python_task", "python", "bound.py", b"print('resource-python-e2e')"),
        ("shell_task", "shell", "bound.sh", b"printf resource-shell-e2e"),
    )
    refs = []
    for task_id, kind, filename, content in fixtures:
        resource = upload(project_id, kind, filename, content, token)
        ref = {"resourceId": int(resource["resource_id"]), "version": int(resource["version"])}
        params = {"sourceMode": "resource", "resourceRef": ref}
        if kind == "sql":
            params["execute"] = True
        call(f"{BASE}/workflows/{workflow_id}/nodes", token, "POST", {
            "project_id": project_id,
            "node_code": task_id,
            "node_type": kind,
            "component_ref": {"type": kind, "version": versions[kind]},
            "params": params,
        })
        call(f"{BASE}/resources/bindings", token, "POST", {
            "project_id": project_id,
            "workflow_id": workflow_id,
            "workflow_version": 1,
            "task_id": task_id,
            "resource_id": ref["resourceId"],
            "resource_version": ref["version"],
        })
        refs.append(ref)
    snapshot = call(f"{BASE}/trial/definitions/{workflow_id}/snapshot", token, "POST", {"project_id": project_id})
    result = call(f"{BASE}/trial/definitions/{workflow_id}/run", token, "POST", {
        "project_id": project_id,
        "snapshot_id": snapshot["snapshot_id"],
        "options": {"sql_execute": True},
    })
    if result["status"] != "SUCCEEDED" or result["task_count"] != 3:
        raise RuntimeError(f"unexpected trial result: {result}")
    print(json.dumps({
        "project_id": project_id,
        "workflow_id": workflow_id,
        "instance_id": result["instance_id"],
        "snapshot_id": snapshot["snapshot_id"],
        "status": result["status"],
        "task_count": result["task_count"],
        "resource_versions": refs,
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()

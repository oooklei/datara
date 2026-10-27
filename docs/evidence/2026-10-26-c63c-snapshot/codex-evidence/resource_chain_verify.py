import json
import sys
from urllib.request import Request, urlopen

token = open(sys.argv[1], encoding="utf-8").read().strip()
state = json.loads(open(sys.argv[2], encoding="utf-8").read())
host = sys.argv[3]
path = f"http://{host}/api/v1/rebuild/trial/definitions/{state['workflow_id']}/run"
body = json.dumps({
    "project_id": state["project_id"],
    "snapshot_id": state["snapshot_id"],
    "options": {"sql_execute": True},
}).encode()
request = Request(path, data=body, method="POST", headers={
    "Authorization": f"Bearer {token}", "Content-Type": "application/json"
})
with urlopen(request, timeout=30) as response:
    result = json.loads(response.read())["data"]
if result["status"] != "SUCCEEDED" or result["task_count"] != 3:
    raise RuntimeError(result)
print(json.dumps({"post_restart_status": result["status"], "task_count": result["task_count"]}, separators=(",", ":")))

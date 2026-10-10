import urllib.request
import json

API = "http://192.168.1.9:8000/api/v1"
r = urllib.request.urlopen(
    urllib.request.Request(
        API + "/login",
        data=json.dumps({"user_name": "admin", "user_pwd": "Admin@123"}).encode(),
        headers={"Content-Type": "application/json"},
    ),
    timeout=10,
)
TOKEN = json.loads(r.read())["data"]["token"]

# Try run with wf_id
req = urllib.request.Request(
    API + "/workflow-definitions/wf_8182a5d0/run",
    data=json.dumps({"priority": 3}).encode(),
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        r = json.loads(resp.read())
        print(json.dumps(r, ensure_ascii=False)[:800])
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()[:500]}")

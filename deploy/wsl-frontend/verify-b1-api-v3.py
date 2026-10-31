#!/usr/bin/env python3
"""B1 dry-run 闭环验收脚本 v3"""
import os, sys, json, time, urllib.request, urllib.parse

HOST = "http://192.168.1.9:8090"
KEY_PATH = ".vk"
SCOPE = "high-priority-e2e"
PROJECT_ID = 33
WF_CODE = 188282273576704

def api(method, path, token=None, params=None, body=None, extra_headers=None, timeout=15):
    url = HOST + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["token"] = token
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

# 1. Get token
print("1. Getting token...")
key = open(KEY_PATH).read().strip()
resp = api("POST", "/api/v1/rebuild/validation-token",
           extra_headers={
               "X-Backend-Validation-Key": key,
               "X-Backend-Validation-Scope": SCOPE
           })
TOKEN = resp["data"]["token"]
print(f"   token ok ({TOKEN[:16]}...)")

# 2. Start dry-run
print("\n2. Starting dry-run workflow instance...")
start_body = {
    "workflowDefinitionCode": WF_CODE,
    "projectId": PROJECT_ID,
    "dryRun": True,
    "startParams": {}
}
resp = api("POST", "/api/v1/rebuild/orchestration/workflow-instances/start",
           token=TOKEN, body=start_body, timeout=30)
print(f"   -> code={resp.get('code')} msg={resp.get('msg')} data={resp.get('data')}")
assert resp.get("code") == 0, f"start failed: {resp}"
instance_ids = resp["data"]
inst_id = instance_ids[0] if isinstance(instance_ids, list) else instance_ids
print(f"   instance id = {inst_id}")

# 3. Poll state
print(f"\n3. Polling instance {inst_id}...")
target = None
final_state = "UNKNOWN"
for i in range(20):
    time.sleep(2)
    try:
        r = api("GET", f"/api/v1/rebuild/orchestration/workflow-instances/{inst_id}",
                token=TOKEN, params={"project_id": PROJECT_ID})
        d = r.get("data")
        if isinstance(d, dict):
            target = d
            final_state = d.get("state", "?")
        print(f"   poll {i}: state={final_state}")
        if final_state in ("SUCCESS", "FAILURE", "PAUSE", "STOP"):
            break
    except Exception as e:
        print(f"   poll {i}: err {e}")

print(f"   FINAL STATE = {final_state}")
if target:
    print(f"   full state fields: {[k for k in target.keys() if 'state' in k.lower() or 'run' in k.lower()]}")

# 4. Task instances
print(f"\n4. Task instances for instance {inst_id}...")
r = api("GET", "/api/v1/rebuild/orchestration/task-instances",
        token=TOKEN,
        params={"project_id": PROJECT_ID, "workflow_instance_id": inst_id,
                "workflow_code": WF_CODE, "page_no": 1, "page_size": 100})
items = []
d = r.get("data")
if isinstance(d, dict):
    items = d.get("totalList", []) or d.get("list", [])
elif isinstance(d, list):
    items = d
print(f"   TASKS: {len(items)} rows")
success_count = sum(1 for t in items if t.get("state") == "SUCCESS")
fail_count = sum(1 for t in items if t.get("state") == "FAILURE")
other_count = len(items) - success_count - fail_count
print(f"   SUCCESS={success_count} FAILURE={fail_count} OTHER={other_count}")
for t in items:
    print(f"     id={t.get('id')} name={t.get('name')} state={t.get('state')} host={t.get('host')} logPath={t.get('logPath')}")

# 5. Gantt
print(f"\n5. Gantt...")
try:
    r = api("GET", f"/api/v1/rebuild/orchestration/workflow-instances/{inst_id}/gantt",
            token=TOKEN, params={"project_id": PROJECT_ID})
    g = r.get("data")
    if isinstance(g, dict):
        keys = list(g.keys())[:8]
        print(f"   keys={keys}")
        til = g.get("taskInstances") or g.get("taskList") or []
        print(f"   taskInstances count={len(til)}")
    elif isinstance(g, list):
        print(f"   list len={len(g)}")
    else:
        print(f"   type={type(g).__name__}")
except Exception as e:
    print(f"   err: {e}")

# 6. Log for a success task
if success_count > 0:
    success_tasks = [t for t in items if t.get("state") == "SUCCESS"]
    for t in success_tasks[:2]:
        tid = t.get("id")
        tname = t.get("name")
        print(f"\n6. Log for task {tid} ({tname})...")
        try:
            r = api("GET", f"/api/v1/rebuild/orchestration/task-instances/{tid}/log",
                    token=TOKEN,
                    params={"project_id": PROJECT_ID, "skip_line_num": 0, "limit": 50})
            d = r.get("data")
            if isinstance(d, dict):
                log_content = d.get("log") or d.get("logContent") or d.get("content") or d.get("taskLog") or ""
                if isinstance(log_content, str):
                    print(f"   log ({len(log_content)} chars):")
                    for line in log_content.split("\n")[:15]:
                        print(f"     {line[:120]}")
                elif isinstance(log_content, list):
                    for ln in log_content[:10]:
                        print(f"     {ln}")
                else:
                    print(f"   data keys={list(d.keys())[:12]}")
                    print(f"   raw data snippet={str(d)[:300]}")
            elif isinstance(d, str):
                print(f"   log ({len(d)} chars):")
                for line in d.split("\n")[:15]:
                    print(f"     {line[:120]}")
            else:
                print(f"   data type={type(d).__name__} raw={str(r)[:300]}")
        except Exception as e:
            print(f"   err: {e}")
else:
    print("\n6. No successful tasks to get log.")

# 7. Summary
print("\n" + "="*60)
print("B1 DRY-RUN VERIFICATION SUMMARY")
print("="*60)
print(f"Instance #{inst_id}: {final_state}")
print(f"Tasks: {len(items)} total, {success_count} SUCCESS, {fail_count} FAILURE")
if final_state == "SUCCESS" and fail_count == 0 and len(items) > 0:
    print("RESULT: PASS ✅")
    sys.exit(0)
else:
    print("RESULT: FAIL ❌")
    sys.exit(1)

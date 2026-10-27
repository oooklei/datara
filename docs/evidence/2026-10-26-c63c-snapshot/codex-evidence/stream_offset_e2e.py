import json
import sys
import time
from urllib.request import Request, urlopen

base, token_file = sys.argv[1:3]
token = open(token_file, encoding="utf-8").read().strip()


def call(path, body):
    request = Request(
        base + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    if payload.get("code") != 0:
        raise RuntimeError(payload)
    return payload["data"]


stamp = time.strftime("%Y%m%d%H%M%S")
job = call("/api/v1/rebuild/stream/jobs", {
    "name": f"stream-offset-e2e-{stamp}",
    "workflow_id": 424242,
    "mq_topic": f"datara.offset.{stamp}",
    "runtime_config": {"mode": "fixed_rate", "rows_per_sec": 10, "columns": ["id", "value"]},
})
job_id = job["id"]
call(f"/api/v1/rebuild/stream/jobs/{job_id}/transitions", {"action": "start"})
call(f"/api/v1/rebuild/stream/jobs/{job_id}/transitions", {"action": "activate"})
first = call(f"/api/v1/rebuild/stream/jobs/{job_id}/produce", {
    "count": 2, "partition_id": "p1", "start_offset": 10, "payload": {"value": 1}
})
second = call(f"/api/v1/rebuild/stream/jobs/{job_id}/produce", {
    "count": 2, "partition_id": "p1", "payload": {"value": 2}
})
if first["last_offset"] != 11 or second["last_offset"] != 13:
    raise RuntimeError({"first": first, "second": second})
print(json.dumps({"job_id": job_id, "first_last_offset": 11, "resumed_last_offset": 13}, separators=(",", ":")))

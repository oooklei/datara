import json
import os
import subprocess
import sys
from urllib.request import Request, urlopen

key = subprocess.run(
    ["docker", "exec", "datara-rebuild-api", "printenv", "REBUILD_VALIDATION_KEY"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
request = Request(
    "http://127.0.0.1:18091/api/v1/rebuild/validation-token",
    data=b"{}",
    headers={
        "Content-Type": "application/json",
        "X-Backend-Validation-Key": key,
        "X-Backend-Validation-Scope": "high-priority-e2e",
    },
    method="POST",
)
with urlopen(request, timeout=15) as response:
    data = json.loads(response.read().decode())["data"]
    token = data["token"]
if data["user"]["role"] != "admin" or data.get("capability") is not None:
    raise RuntimeError("validation endpoint did not issue the requested E2E admin scope")
target = sys.argv[1]
with open(target, "w", encoding="utf-8") as stream:
    stream.write(token)
os.chmod(target, 0o600)
print("TOKEN_ISSUED role=admin ttl=900")

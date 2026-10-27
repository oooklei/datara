#!/bin/sh
set -eu

evidence_dir=/lei/datara/evidence/ide-schema-01
mkdir -p "$evidence_dir"
validation_key=$(docker exec datara-rebuild-api printenv REBUILD_VALIDATION_KEY)
issued=$(curl -fsS -X POST \
  -H "X-Backend-Validation-Key: $validation_key" \
  -H "X-Backend-Validation-Scope: high-priority-e2e" \
  http://127.0.0.1:18091/api/v1/rebuild/validation-token)
token=$(printf '%s' "$issued" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["token"])')
http_code=$(curl -sS -o "$evidence_dir/execution.json" -w '%{http_code}' -X POST \
  -H "Authorization: Bearer $token" \
  -H 'Content-Type: application/json' \
  --data '{"datasourceId":17,"sql":"select 1 as ide_schema_repaired","mode":"auto"}' \
  http://127.0.0.1:18091/api/v1/projects/27/sql-ide/executions)
curl -fsS -X POST -H "Authorization: Bearer $token" \
  http://127.0.0.1:18091/api/v1/rebuild/logout > "$evidence_dir/logout.json"
unset token validation_key issued
HTTP_CODE="$http_code" python3 - <<'PY'
import json
import os

path = "/lei/datara/evidence/ide-schema-01/execution.json"
payload = json.load(open(path, encoding="utf-8"))
data = payload.get("data", {})
print(json.dumps({"http": os.environ["HTTP_CODE"], "code": payload.get("code"), "keys": sorted(data)[:8]}))
PY

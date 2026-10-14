#!/usr/bin/env bash
set -euo pipefail

project_id="${1:-}"
if [[ ! "$project_id" =~ ^[0-9]+$ ]]; then
  echo 'usage: r1_remote_runtime_evidence.sh <created_project_id>' >&2
  exit 2
fi

echo "R1_REMOTE_EVIDENCE_AT=$(date -Is)"
docker exec datara-mysql-meta sh -lc "export MYSQL_PWD=\"\$MYSQL_ROOT_PASSWORD\"; mysql -uroot -N -e \"SELECT id,owner_id,name,created_at,updated_at FROM datara_rebuild_i0.rebuild_project WHERE id=${project_id}\""
echo '--- rebuild API request summary (last 20 minutes) ---'
docker logs --since 20m datara-rebuild-api 2>&1 | grep -E 'POST /api/v1/rebuild/(validation-token|projects|datasources/profiles|logout)|GET /api/v1/rebuild/projects' | tail -30 || true
echo '--- runtime health ---'
docker inspect -f '{{.State.Status}} {{.State.Health.Status}}' datara-rebuild-api
curl -fsS http://127.0.0.1:18091/api/v1/rebuild/health
echo

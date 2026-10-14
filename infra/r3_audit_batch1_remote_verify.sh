#!/usr/bin/env bash
set -euo pipefail

printf 'R3_AUDIT_BATCH1_REMOTE_VERIFY_AT=%s\n' "$(date -Is)"
docker inspect -f 'legacy_api_status={{.State.Status}} legacy_api_health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' datara-api
docker exec datara-api python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen("http://127.0.0.1:8000/openapi.json")); paths=sorted(p for p in d["paths"] if "/qc" in p.lower()); print("legacy_qc_openapi_routes=%d" % len(paths)); print("legacy_qc_paths=" + ",".join(paths)); assert not paths'
docker exec datara-api sh -lc 'curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null && echo legacy_api_health_endpoint=UP'

docker exec -i datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -N -B datara_meta' <<'SQL'
SELECT table_name, COUNT(*) AS table_exists
FROM information_schema.tables
WHERE table_schema=DATABASE()
  AND table_name IN ('t_qc_rule','t_qc_task','t_qc_run','t_qc_exception','t_qc_report','t_qc_alarm_policy')
GROUP BY table_name ORDER BY table_name;
SELECT 't_qc_rule', COUNT(*) FROM t_qc_rule;
SELECT 't_qc_task', COUNT(*) FROM t_qc_task;
SELECT 't_qc_run', COUNT(*) FROM t_qc_run;
SELECT 't_qc_exception', COUNT(*) FROM t_qc_exception;
SELECT 't_qc_report', COUNT(*) FROM t_qc_report;
SELECT 't_qc_alarm_policy', COUNT(*) FROM t_qc_alarm_policy;
SQL

docker inspect -f 'rebuild_api_status={{.State.Status}} rebuild_api_health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' datara-rebuild-api
docker exec datara-rebuild-api python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen("http://127.0.0.1:8001/openapi.json")); n=sum(p.startswith("/api/v1/rebuild/governance/") for p in d["paths"]); print("rebuild_governance_routes=%d" % n); assert n == 11'
docker logs --since=10m datara-api 2>&1 | awk '/ERROR|Traceback|Exception/ {n++} END {printf "legacy_api_error_markers_10m=%d\n", n+0}'
docker logs --since=168h datara-api 2>&1 | awk '/\/api\/v1\/qc\// {n++} END {printf "legacy_qc_route_log_hits_7d=%d\n", n+0}'
docker logs --since=10m datara-rebuild-api 2>&1 | awk '/ERROR|Traceback|Exception/ {n++} END {printf "rebuild_api_error_markers_10m=%d\n", n+0}'
printf 'R3_AUDIT_BATCH1_READONLY_VERIFY_COMPLETE (no DML, no deployment, no restart)\n'
exit 0

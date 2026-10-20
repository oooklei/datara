#!/usr/bin/env bash
set -euo pipefail

project_id="${1:?project id required}"
source_id="${2:?source asset id required}"
target_id="${3:?target asset id required}"
tag_id="${4:?tag id required}"
rule_id="${5:?quality rule id required}"
lineage_id="${6:?lineage edge id required}"
standard_id="${7:?standard id required}"
metric_id="${8:?metric id required}"
audit_from="${9:?audit timestamp lower bound required}"
audit_to="${10:?audit timestamp upper bound required}"

for value in "$project_id" "$source_id" "$target_id" "$tag_id" "$rule_id" "$lineage_id" "$standard_id" "$metric_id"; do
  [[ "$value" =~ ^[0-9]+$ ]] || { echo 'invalid numeric identifier' >&2; exit 2; }
done
[[ "$audit_from" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2}:[0-9]{2}$ ]] || exit 2
[[ "$audit_to" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2}:[0-9]{2}$ ]] || exit 2

printf 'R3_S7_RECONCILE_AT=%s project_id=%s\n' "$(date -Is)" "$project_id"
docker exec -i datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -N -B datara_rebuild_i0' <<SQL
SELECT 'assets', COUNT(*), SUM(created_at IS NULL), SUM(updated_at IS NULL)
FROM rebuild_governance_asset WHERE project_id=$project_id AND id IN ($source_id,$target_id);
SELECT id, project_id, asset_name, created_at, updated_at FROM rebuild_governance_asset
WHERE project_id=$project_id AND id IN ($source_id,$target_id) ORDER BY id;
SELECT 'fields', COUNT(*), SUM(created_at IS NULL), SUM(updated_at IS NULL)
FROM rebuild_governance_asset_field WHERE asset_id IN ($source_id,$target_id);
SELECT id, asset_id, field_name, ordinal_position, created_at, updated_at FROM rebuild_governance_asset_field
WHERE asset_id IN ($source_id,$target_id) ORDER BY asset_id, ordinal_position;
SELECT 'tags', COUNT(*), SUM(created_at IS NULL), SUM(updated_at IS NULL)
FROM rebuild_governance_tag WHERE project_id=$project_id AND id=$tag_id;
SELECT id, project_id, tag_key, display_name, created_at, updated_at FROM rebuild_governance_tag
WHERE project_id=$project_id AND id=$tag_id;
SELECT 'asset_tag_links', COUNT(*), SUM(created_at IS NULL), SUM(updated_at IS NULL)
FROM rebuild_governance_asset_tag WHERE tag_id=$tag_id AND asset_id IN ($source_id,$target_id);
SELECT id, asset_id, tag_id, created_at, updated_at FROM rebuild_governance_asset_tag
WHERE tag_id=$tag_id AND asset_id IN ($source_id,$target_id);
SELECT 'quality_rules', COUNT(*), SUM(created_at IS NULL), SUM(updated_at IS NULL)
FROM rebuild_governance_quality_rule WHERE project_id=$project_id AND id=$rule_id;
SELECT id, project_id, asset_id, name, created_at, updated_at FROM rebuild_governance_quality_rule
WHERE project_id=$project_id AND id=$rule_id;
SELECT 'quality_runs', COUNT(*), SUM(generated_at IS NULL)
FROM rebuild_governance_quality_run WHERE project_id=$project_id AND asset_id IN ($source_id,$target_id);
SELECT 'lineage', COUNT(*), SUM(created_at IS NULL), SUM(updated_at IS NULL)
FROM rebuild_governance_lineage_edge WHERE project_id=$project_id AND id=$lineage_id
  AND source_asset_id=$source_id AND target_asset_id=$target_id;
SELECT id, project_id, source_asset_id, target_asset_id, external_id, created_at, updated_at
FROM rebuild_governance_lineage_edge WHERE project_id=$project_id AND id=$lineage_id;
SELECT 'standards', COUNT(*), SUM(created_at IS NULL), SUM(updated_at IS NULL)
FROM rebuild_governance_standard WHERE project_id=$project_id AND id=$standard_id;
SELECT id, project_id, code, created_at, updated_at FROM rebuild_governance_standard
WHERE project_id=$project_id AND id=$standard_id;
SELECT 'metrics', COUNT(*), SUM(created_at IS NULL), SUM(updated_at IS NULL)
FROM rebuild_governance_semantic_metric WHERE project_id=$project_id AND id=$metric_id;
SELECT id, project_id, code, created_at, updated_at FROM rebuild_governance_semantic_metric
WHERE project_id=$project_id AND id=$metric_id;
SELECT 'audit_window', COUNT(*), SUM(generated_at IS NULL)
FROM rebuild_governance_audit_event WHERE project_id=$project_id
  AND generated_at BETWEEN '$audit_from' AND '$audit_to';
SELECT id, action, resource_type, resource_id, generated_at
FROM rebuild_governance_audit_event WHERE project_id=$project_id
  AND generated_at BETWEEN '$audit_from' AND '$audit_to'
ORDER BY generated_at, id;
SQL

docker inspect -f 'api_status={{.State.Status}} api_health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' datara-rebuild-api
docker logs --since=10m datara-rebuild-api 2>&1 | awk '/ERROR|Traceback|Exception/ {n++} END {printf "api_log_error_markers_10m=%d\n", n+0}'
printf 'S7_DB_RECONCILIATION_COMPLETE (read-only; no DML issued)\n'
exit 0

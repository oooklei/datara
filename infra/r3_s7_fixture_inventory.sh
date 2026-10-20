#!/usr/bin/env bash
set -euo pipefail

printf 'R3_S7_FIXTURE_INVENTORY_AT=%s\n' "$(date -Is)"
docker exec datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -N -B -e "
SELECT id, name, owner_id, created_at, updated_at
FROM datara_rebuild_i0.rebuild_project
ORDER BY id;
SELECT id, project_id, user_id, role, created_at, updated_at
FROM datara_rebuild_i0.rebuild_project_member
ORDER BY id;
"'

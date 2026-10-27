#!/bin/sh
set -eu
docker exec datara-mysql-meta sh -lc 'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SELECT TABLE_SCHEMA,TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA LIKE '\''datara%'\'' AND TABLE_NAME LIKE '\''%llm%'\'' ORDER BY 1,2" 2>/dev/null'
docker exec datara-mysql-meta sh -lc 'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='\''datara_rebuild_candidate'\'' AND TABLE_NAME='\''rebuild_llm_model'\'' ORDER BY ORDINAL_POSITION" 2>/dev/null'
docker exec datara-mysql-meta sh -lc 'for db in datara_rebuild_candidate datara_rebuild_candidate2 datara_rebuild_candidate3 datara_rebuild_candidate4 datara_rebuild_candidate5 datara_rebuild_codex datara_rebuild_i0; do mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SELECT '\''$db'\'',COUNT(*) FROM $db.rebuild_llm_model" 2>/dev/null || true; done'
for c in datara-api datara-rebuild-api; do
  echo "CONTAINER=$c"
  docker inspect "$c" --format '{{range .Config.Env}}{{println .}}{{end}}' | cut -d= -f1 | grep -Ei 'LLM|ARK|SILICON|LONGCAT' || true
done
docker exec datara-mysql-meta sh -lc 'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SELECT DISTINCT TABLE_SCHEMA,TABLE_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA LIKE '\''datara%'\'' AND COLUMN_NAME IN ('\''api_base'\'','\''model_id'\'','\''provider'\'') ORDER BY 1,2" 2>/dev/null'
for c in $(docker ps -a --format '{{.Names}}' | grep 'datara-rebuild-api'); do
  db=$(docker inspect "$c" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^REBUILD_DB_URL=' | sed 's/[?].*$//' | sed 's#.*/##')
  echo "API_DB=$c:$db"
done

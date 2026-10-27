#!/usr/bin/env sh
set -eu
docker exec datara-mysql-meta sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" datara_rebuild_i0 -Nse "SHOW COLUMNS FROM lineage_writeback"'

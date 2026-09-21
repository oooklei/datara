#!/bin/bash
echo "=== mysql-replication 版本 ==="
docker exec -e PYTHONPATH=/app datara-worker pip show mysql-replication 2>/dev/null | head -2
echo "=== src 库 binlog_row_metadata / binlog_row_image ==="
docker exec datara-mysql-src mysql -uroot -pdatara_2026 -N -e "SELECT @@binlog_row_metadata, @@binlog_row_image;"

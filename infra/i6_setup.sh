#!/usr/bin/env bash
# I6 实测场景准备（设计文档 §10 门 #1）：src 实例建 ec_retail_east / ec_retail_south 两 schema
# 同名表 ods_order_sync_src 各灌不同行数（east=500 / south=300，金额列值域可区分）。
# 用法：bash i6_setup.sh            → 建 east/south 并灌数（幂等：先 DROP 再建）
#       bash i6_setup.sh north      → 门 #7 运行时探测用：追加第三 schema ec_retail_north（200 行）
# 行数对账输出 = 源基准清单。
set -e

SH="$1"

run_sql() {
  # "$@" 必须透传：run_sql -e "SQL" 形态依赖它；缺失时 mysql 进交互模式挂在 stdin 上
  docker exec -i datara-mysql-src mysql -uroot -pdatara_2026 --default-character-set=utf8mb4 "$@" 2>/dev/null
}

if [ "$SH" = "north" ]; then
  echo "=== 门 #7 探测场景：追加 ec_retail_north（200 行）==="
  run_sql <<'SQL'
CREATE DATABASE IF NOT EXISTS ec_retail_north;
CREATE TABLE IF NOT EXISTS ec_retail_north.ods_order_sync_src (
  id INT PRIMARY KEY,
  order_no VARCHAR(64),
  amount DECIMAL(12,2),
  create_time DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
SQL
  run_sql <<'SQL'
INSERT INTO ec_retail_north.ods_order_sync_src (id, order_no, amount, create_time)
SELECT n, CONCAT('N', LPAD(n, 6, '0')), ROUND(100 + n * 0.3, 2), DATE_ADD('2026-03-01', INTERVAL n MINUTE)
FROM (WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 200) SELECT n FROM seq) s
WHERE NOT EXISTS (SELECT 1 FROM ec_retail_north.ods_order_sync_src WHERE id = n);
SQL
  echo "--- north 行数 ---"
  run_sql -e "SELECT COUNT(*) AS north_rows FROM ec_retail_north.ods_order_sync_src;"
  exit 0
fi

echo "=== 门 #1 场景准备：ec_retail_east(500) / ec_retail_south(300) ==="
run_sql <<'SQL'
DROP DATABASE IF EXISTS ec_retail_east;
DROP DATABASE IF EXISTS ec_retail_south;
CREATE DATABASE ec_retail_east;
CREATE DATABASE ec_retail_south;
CREATE TABLE ec_retail_east.ods_order_sync_src (
  id INT PRIMARY KEY,
  order_no VARCHAR(64),
  amount DECIMAL(12,2),
  create_time DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ec_retail_south.ods_order_sync_src (
  id INT PRIMARY KEY,
  order_no VARCHAR(64),
  amount DECIMAL(12,2),
  create_time DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
SQL
run_sql <<'SQL'
INSERT INTO ec_retail_east.ods_order_sync_src (id, order_no, amount, create_time)
SELECT n, CONCAT('E', LPAD(n, 6, '0')), ROUND(n * 1.5, 2), DATE_ADD('2026-01-01', INTERVAL n MINUTE)
FROM (WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 500) SELECT n FROM seq) s;
INSERT INTO ec_retail_south.ods_order_sync_src (id, order_no, amount, create_time)
SELECT n, CONCAT('S', LPAD(n, 6, '0')), ROUND(1000 + n * 2.5, 2), DATE_ADD('2026-02-01', INTERVAL n MINUTE)
FROM (WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 300) SELECT n FROM seq) s;
SQL
echo "--- 源基准清单 ---"
run_sql -e "SELECT 'ec_retail_east' AS src, COUNT(*) AS rows_cnt, ROUND(SUM(amount),2) AS amount_sum FROM ec_retail_east.ods_order_sync_src UNION ALL SELECT 'ec_retail_south', COUNT(*), ROUND(SUM(amount),2) FROM ec_retail_south.ods_order_sync_src;"
echo "I6_SETUP_DONE"

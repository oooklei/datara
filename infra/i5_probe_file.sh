#!/usr/bin/env bash
# I5 门#10 前置探测：file 数据源 + 样例文件表头
META="docker exec datara-mysql-meta mysql -uroot -pdatara_2026 datara_meta --default-character-set=utf8mb4 -N -e"

echo "=== 1. file 类型数据源（name + params）==="
$META "SELECT id, name, params FROM t_data_source WHERE type='file';" 2>/dev/null

echo "=== 2. worker 容器内共享卷文件 ==="
docker exec datara-worker sh -c "find /datara/files -type f | head -20"

echo "=== 3. 样例文件表头 ==="
for f in $(docker exec datara-worker sh -c "find /datara/files/samples -type f 2>/dev/null"); do
  echo "--- $f ---"
  docker exec datara-worker sh -c "head -2 '$f'"
done

echo "=== 4. datara_dw 目标库容器核对 ==="
docker ps --format '{{.Names}} {{.Ports}}' | grep -i 'dw\|3309'
echo "PROBE_DONE"

#!/bin/bash
echo "=== 容器状态 ==="
docker ps --format '{{.Names}}\t{{.Status}}' | grep datara
echo "=== worker 流引擎启动日志 ==="
docker logs datara-worker --tail 8 2>&1 | grep -E "流引擎|flink|worker 模块" || docker logs datara-worker --tail 5 2>&1
echo "=== 依赖验证（worker 容器内）==="
docker exec datara-worker python -c "import kafka, pymysqlreplication; print('kafka-python OK, mysql-replication OK')"
echo "=== API 健康 ==="
curl -s http://localhost:8000/api/v1/health | head -c 200; echo
echo "=== t_stream_job 表就绪 ==="
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "SELECT COUNT(*) FROM datara_meta.information_schema.tables WHERE table_name IN ('t_stream_job','t_stream_offset') AND table_schema=DATABASE();" 2>/dev/null
docker exec datara-mysql-meta mysql -uroot -pdatara_2026 -N -e "SELECT table_name FROM information_schema.tables WHERE table_schema='datara_meta' AND table_name LIKE 't_stream%';" 2>/dev/null
echo "=== web 页面 ==="
curl -s -o /dev/null -w "http_code=%{http_code}\n" http://localhost:8090/

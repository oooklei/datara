#!/bin/bash
# I8 部署前置：mysql-src binlog 检查 + 复制账号 + Kafka KRaft 容器（设计文档 §12）
set -e
MY="docker exec datara-mysql-src mysql -uroot -pdatara_2026 --default-character-set=utf8mb4"

echo "=== 1. mysql-src binlog 状态 ==="
$MY -N -e "SELECT CONCAT('log_bin=', @@log_bin, ' server_id=', @@server_id, ' binlog_format=', @@binlog_format, ' gtid_mode=', @@gtid_mode, ' binlog_row_image=', @@binlog_row_image);" 2>/dev/null

echo "=== 2. binlog 复制账号（repl/datara_repl_2026）==="
$MY 2>/dev/null <<'SQL'
CREATE USER IF NOT EXISTS 'repl'@'%' IDENTIFIED WITH mysql_native_password BY 'datara_repl_2026';
GRANT REPLICATION SLAVE, REPLICATION CLIENT, SELECT ON *.* TO 'repl'@'%';
FLUSH PRIVILEGES;
SELECT user, host FROM mysql.user WHERE user='repl';
SQL

echo "=== 3. kafka 镜像拉取状态 ==="
if docker images | grep -q bitnami/kafka; then
  docker images | grep bitnami/kafka
else
  echo "镜像未就绪，当前 pull 进度："
  tail -2 /tmp/kafka-pull.log || true
  exit 9
fi

echo "=== 4. Kafka KRaft 容器（datara-kafka:9092）==="
if docker ps -a --format '{{.Names}}' | grep -q '^datara-kafka$'; then
  docker start datara-kafka && echo "已有容器已启动"
else
  docker run -d --name datara-kafka \
    --network datara_default \
    -e KAFKA_CFG_NODE_ID=0 \
    -e KAFKA_CFG_PROCESS_ROLES=controller,broker \
    -e KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=0@datara-kafka:9093 \
    -e KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093 \
    -e KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://datara-kafka:9092 \
    -e KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT \
    -e KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER \
    -e KAFKA_CFG_INTER_BROKER_LISTENER_NAME=PLAINTEXT \
    -e KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE=true \
    bitnami/kafka:3.7
fi
sleep 8
docker exec datara-kafka kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic datara-demo-orders --partitions 1 --replication-factor 1 && echo "演示 topic datara-demo-orders 就绪"
docker exec datara-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list
echo "=== I8 部署前置完成 ==="

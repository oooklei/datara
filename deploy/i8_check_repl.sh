#!/bin/bash
MY="docker exec datara-mysql-src mysql -uroot -pdatara_2026"
echo "=== 创建 repl（显示错误）==="
$MY -e "CREATE USER IF NOT EXISTS 'repl'@'%' IDENTIFIED BY 'datara_repl_2026';" 2>&1 | grep -v "password on the command line"
$MY -e "GRANT REPLICATION SLAVE, REPLICATION CLIENT, SELECT ON *.* TO 'repl'@'%'; FLUSH PRIVILEGES;" 2>&1 | grep -v "password on the command line"
$MY -e "SELECT user, host, plugin FROM mysql.user WHERE user='repl'; SHOW GRANTS FOR 'repl'@'%';" 2>&1 | grep -v "password on the command line"

#!/usr/bin/env bash
set -euo pipefail

docker exec datara-mysql-src mysql -uroot -pdatara_2026 -N -e \
  "SELECT COUNT(*) FROM ec_retail.ods_payment p JOIN ec_retail.ods_order o ON p.order_id=o.id WHERE p.pay_time < o.create_time;"
docker exec datara-mysql-src mysql -uroot -pdatara_2026 -N -e \
  "SELECT p.id,p.order_id,p.pay_time,o.create_time FROM ec_retail.ods_payment p JOIN ec_retail.ods_order o ON p.order_id=o.id WHERE p.pay_time < o.create_time ORDER BY p.id LIMIT 20;"

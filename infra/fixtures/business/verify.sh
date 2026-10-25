#!/usr/bin/env bash
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/common.sh"

mode="${1:-prepared}"
case "$mode" in prepared|synced) ;; *) die "usage: $0 [prepared|synced]" ;; esac
assert_validation_host
assert_runtime

source_counts="$(mysql_scalar "$SRC_SERVICE" ec_retail "SELECT CONCAT((SELECT COUNT(*) FROM dim_user WHERE id BETWEEN 910001 AND 910099),',',(SELECT COUNT(*) FROM dim_goods WHERE id BETWEEN 910001 AND 910099),',',(SELECT COUNT(*) FROM ods_order WHERE id BETWEEN 910000000001 AND 910000000099),',',(SELECT COUNT(*) FROM ods_order_item WHERE id BETWEEN 910000000101 AND 910000000199),',',(SELECT COUNT(*) FROM ods_payment WHERE id BETWEEN 910000000201 AND 910000000299),',',(SELECT COUNT(*) FROM fixture_order_detail_source));")"
[ "$source_counts" = "2,3,3,4,2,4" ] || die "source counts mismatch: $source_counts (expected 2,3,3,4,2,4)"

source_issues="$(mysql_scalar "$SRC_SERVICE" ec_retail "SELECT (SELECT COUNT(*) FROM ods_order o LEFT JOIN dim_user u ON u.id=o.user_id WHERE o.id BETWEEN 910000000001 AND 910000000099 AND u.id IS NULL)+(SELECT COUNT(*) FROM ods_order_item i LEFT JOIN ods_order o ON o.id=i.order_id AND o.order_date=i.order_date LEFT JOIN dim_goods g ON g.id=i.goods_id WHERE i.id BETWEEN 910000000101 AND 910000000199 AND (o.id IS NULL OR g.id IS NULL))+(SELECT COUNT(*) FROM ods_payment p LEFT JOIN ods_order o ON o.id=p.order_id WHERE p.id BETWEEN 910000000201 AND 910000000299 AND o.id IS NULL);")"
[ "$source_issues" = "0" ] || die "source relationship issues: $source_issues"

expected_count="$(mysql_scalar "$DW_SERVICE" datara_dw "SELECT COUNT(*) FROM fixture_order_detail_expected WHERE fixture_key='INFRA-DATA-01';")"
[ "$expected_count" = "4" ] || die "target expected baseline count mismatch: $expected_count"

actual_count="$(mysql_scalar "$DW_SERVICE" datara_dw "SELECT COUNT(*) FROM fixture_order_detail_actual WHERE fixture_key='INFRA-DATA-01';")"
if [ "$mode" = "prepared" ]; then
  [ "$actual_count" = "0" ] || die "prepared target must be empty, found $actual_count rows"
  log "verified prepared baseline: source=2 users/3 goods/3 orders/4 items/2 payments; target expected=4, actual=0"
  exit 0
fi

[ "$actual_count" = "4" ] || die "synced target count mismatch: $actual_count (expected 4)"
mismatches="$(mysql_scalar "$DW_SERVICE" datara_dw "SELECT COUNT(*) FROM ((SELECT e.item_id FROM fixture_order_detail_expected e LEFT JOIN fixture_order_detail_actual a ON a.item_id=e.item_id AND a.fixture_key=e.fixture_key AND a.order_id=e.order_id AND a.order_no=e.order_no AND a.user_id=e.user_id AND a.username=e.username AND a.goods_id=e.goods_id AND a.goods_name=e.goods_name AND a.qty=e.qty AND a.unit_price=e.unit_price AND a.item_amount=e.item_amount AND a.order_status=e.order_status AND a.pay_channel<=>e.pay_channel AND a.pay_amount<=>e.pay_amount AND a.order_date=e.order_date WHERE e.fixture_key='INFRA-DATA-01' AND a.item_id IS NULL) UNION ALL (SELECT a.item_id FROM fixture_order_detail_actual a LEFT JOIN fixture_order_detail_expected e ON e.item_id=a.item_id AND e.fixture_key=a.fixture_key WHERE a.fixture_key='INFRA-DATA-01' AND e.item_id IS NULL)) x;")"
[ "$mismatches" = "0" ] || die "target differs from expected baseline: $mismatches mismatched rows"
log "verified synced baseline: 4 target rows exactly match expected values"

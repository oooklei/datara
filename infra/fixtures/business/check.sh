#!/usr/bin/env bash
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/common.sh"

mode="${1:-static}"
case "$mode" in
  static)
    command -v python3 >/dev/null 2>&1 || die "python3 is required for fixture contract checks"
    "$BASH" -n "$FIXTURE_DIR/common.sh" "$FIXTURE_DIR/check.sh" "$FIXTURE_DIR/prepare.sh" "$FIXTURE_DIR/verify.sh"
    python3 "$FIXTURE_DIR/test_fixture_contract.py"
    python3 "$FIXTURE_DIR/seed_product_fixture.py" --dry-run >/dev/null
    log "static fixture contract and shell syntax checks passed"
    ;;
  container)
    assert_validation_host
    assert_runtime
    src_tables="$(mysql_scalar "$SRC_SERVICE" ec_retail "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='ec_retail' AND table_name IN ('dim_user','dim_goods','ods_order','ods_order_item','ods_payment');")"
    [ "$src_tables" = "5" ] || die "source schema is missing required tables: found $src_tables/5"
    dw_schema="$(mysql_scalar "$DW_SERVICE" datara_dw "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='datara_dw';")"
    [ "$dw_schema" = "1" ] || die "target schema datara_dw is unavailable"
    log "container preflight passed on 192.168.1.9: compose services running, source tables=5, target schema=present"
    ;;
  *) die "usage: $0 [static|container]" ;;
esac

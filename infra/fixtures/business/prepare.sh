#!/usr/bin/env bash
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/common.sh"

assert_validation_host
assert_runtime
log "loading deterministic source rows"
mysql_stdin "$SRC_SERVICE" ec_retail < "$FIXTURE_DIR/sql/source.sql"
log "resetting the dedicated target actual table and expected baseline"
mysql_stdin "$DW_SERVICE" datara_dw < "$FIXTURE_DIR/sql/target.sql"
log "prepared: source view=ec_retail.fixture_order_detail_source; target=datara_dw.fixture_order_detail_actual"
log "next: run ./verify.sh prepared, execute the product sync, then ./verify.sh synced"

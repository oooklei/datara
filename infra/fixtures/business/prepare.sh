#!/usr/bin/env bash
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/common.sh"

assert_validation_host
assert_runtime
log "loading deterministic source rows"
mysql_stdin "$SRC_SERVICE" ec_retail < "$FIXTURE_DIR/sql/source.sql"
log "resetting the dedicated target actual table and expected baseline"
mysql_stdin "$DW_SERVICE" datara_dw < "$FIXTURE_DIR/sql/target.sql"
file_sync_target="$REPO_ROOT/files/fixtures/orders_file_sync.csv"
mkdir -p "$(dirname "$file_sync_target")"
cp "$FIXTURE_DIR/files/orders_file_sync.csv" "$file_sync_target"
log "prepared: source view=ec_retail.fixture_order_detail_source; target=datara_dw.fixture_order_detail_actual"
log "prepared: file_sync path=/datara/files/fixtures/orders_file_sync.csv"
log "next: run ./verify.sh prepared, execute the product sync, then ./verify.sh synced"

#!/usr/bin/env bash
set -euo pipefail

target='/lei/datara/datara-web/dist/rebuild-validation-r3.html'
staged='/lei/datara/datara-web/dist/.rebuild-validation-r3.html.new'
old_hash='b8fb79d79c832689385edfb858134c50f64fb2227ac4cd85097a99bf186e3424'
new_hash='aaafb1a792004f57a4ff453ffd447f976d7159537fe066b67d59dd371bec043c'

test "$(sha256sum "$target" | cut -d' ' -f1)" = "$old_hash"
test "$(sha256sum "$staged" | cut -d' ' -f1)" = "$new_hash"
test "$(docker inspect -f '{{.State.Health.Status}}' datara-rebuild-api)" = 'healthy'
backup_dir="$(mktemp -d /lei/datara/backups/r3-s7-XXXXXX)"
chmod 700 "$backup_dir"
cp -p "$target" "$backup_dir/rebuild-validation-r3.html.before"
chmod 600 "$backup_dir/rebuild-validation-r3.html.before"
test "$(sha256sum "$backup_dir/rebuild-validation-r3.html.before" | cut -d' ' -f1)" = "$old_hash"

chmod --reference="$target" "$staged"
chown --reference="$target" "$staged"
mv "$staged" "$target"
test "$(sha256sum "$target" | cut -d' ' -f1)" = "$new_hash"
printf 'R3_S7_PAGE_REPAIR_AT=%s\n' "$(date -Is)"
printf 'page_backup_dir=%s\n' "$backup_dir"
sha256sum "$backup_dir/rebuild-validation-r3.html.before" "$target"
curl -fsS -o /tmp/r3_s7_page_check.html -w 'page_http=%{http_code} content_type=%{content_type} bytes=%{size_download}\n' http://127.0.0.1:18091/rebuild-validation-r3.html
grep -q '数据资产目录' /tmp/r3_s7_page_check.html
grep -q 'Activity / Audit' /tmp/r3_s7_page_check.html
docker inspect -f 'web_status={{.State.Status}} web_health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' datara-web
echo 'R3_S7_PAGE_REPAIR_OK: one file atomically replaced; Web not restarted'

#!/usr/bin/env bash
set -euo pipefail

target='/lei/datara/datara-web/dist/rebuild-validation-r3.html'
staged='/lei/datara/datara-web/dist/.rebuild-validation-r3.html.new'
expected='08bc0e6de51d86d022a3f2becf5c33ed1804bc863dcf5fa8a30f2d2e2df80373'

test ! -e "$target"
test -s "$staged"
test "$(sha256sum "$staged" | cut -d' ' -f1)" = "$expected"
test "$(docker inspect -f '{{.State.Health.Status}}' datara-rebuild-api)" = 'healthy'
route_count="$(docker exec datara-rebuild-api python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen("http://127.0.0.1:8001/openapi.json")); print(sum(p.startswith("/api/v1/rebuild/governance/") for p in d["paths"]))')"
test "$route_count" = '11'

chmod --reference=/lei/datara/datara-web/dist/index.html "$staged"
chown --reference=/lei/datara/datara-web/dist/index.html "$staged"
mv "$staged" "$target"
test "$(sha256sum "$target" | cut -d' ' -f1)" = "$expected"
printf 'R3_S7_PAGE_DEPLOY_AT=%s\n' "$(date -Is)"
curl -fsS -o /tmp/r3_s7_page_check.html -w 'page_http=%{http_code} content_type=%{content_type} bytes=%{size_download}\n' http://127.0.0.1:18091/rebuild-validation-r3.html
grep -q '数据资产目录' /tmp/r3_s7_page_check.html
grep -q 'Activity / Audit' /tmp/r3_s7_page_check.html
sha256sum "$target"
docker inspect -f 'web_status={{.State.Status}} web_health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' datara-web
echo 'R3_S7_STATIC_PAGE_DEPLOY_OK: added one absent static file; no Web restart/rebuild'

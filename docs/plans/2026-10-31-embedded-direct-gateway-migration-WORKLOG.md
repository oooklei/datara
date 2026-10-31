# EMBEDDED DIRECT GATEWAY MIGRATION — Chief-of-Staff Worklog

- **Plan**: `docs/plans/2026-10-31-embedded-direct-gateway-migration.md`
- **DRI**: QA (chief-of-staff mode), started 2026-10-31
- **Scope reality**: This repo = Datara backend gateway + nginx only. DBX & DolphinScheduler are **external containers** (their source is NOT in this workspace). So Phases A (Datara-side token + nginx) are in-repo; container-side token self-verification (§实施规则③/④) and Phase B/C verification depend on external container changes.

## Ground truth (code-explorer map, 2026-10-31)
- `ide_proxy.py`: `datara-backend/rebuild/dbx/ide_proxy.py` — `proxy_ide` (L172) sync urllib → blocks event loop. `issue_ide_session` (L150) sets in-memory opaque cookie (`IdeSessionRegistry`, L40, TTL 900s).
- nginx: `deploy/wsl-frontend/nginx.conf` + `datara-newweb/deploy/nginx.conf` have `/ide/` & `/dolphinscheduler/` pointing at host `192.168.1.9`; `/ide/api/` rewrites → `/api/v1/rebuild/dbx/ide-proxy/`. SSE = `proxy_buffering off`.
- Tokens: `TokenService` (HMAC) `rebuild/identity/contracts.py` (issue L141 / verify L177); DS embed token `_issue_ds_embed_token` `rebuild/orchestration/api.py:168` (claims u/p/d, exp+900s); unified `/embed/session` `orchestration/api.py:699` returns only paths.
- DS patch exists: `deploy/dolphinscheduler/3.4.3/datara-integration.patch` (interceptor parses embed token, forwards X-Datara-User). DBX patch: none in repo.
- Auth: `normalize_token_header` `rebuild/api/app.py:651`; `current_user` + `project_permission_error` per router factory.

## Milestones
- **A — bypass validation (IN-REPO, DONE 2026-10-31)**: unified `POST/GET /api/v1/rebuild/embed/session` issues signed short-lived (900s) project+app-scoped token **AND sets it as HttpOnly cookie `datara_dbx_embed` (path=/ide)** so DBX direct entry works without exposing the token to JS/localStorage/URL (方案规则 1/2); nginx `/ide/` (both `datara-newweb/deploy/nginx.conf` + `deploy/wsl-frontend/nginx.conf`) injects `X-Datara-Embed-Token $cookie_datara_dbx_embed` server-side (方案规则 2); `/ide/api/*` (ide_proxy) kept for rollback. Contract tests added: `test_unified_embed_session_sets_dbx_embed_cookie` + `...degrades_without_signing_secret` (3/3 embed_session tests pass). Subagent `impl-embed-A` 完成后端接缝；chief-of-staff session 补全 DBX 令牌 cookie + nginx 注入。
- **B — default switch (Datara-side + external)**: `/ide/` & `/dolphinscheduler/` default direct; re-issue token on expiry/project|user switch. Needs container-side verification ready.
- **C — decommission (Datara-side)**: remove `ide_proxy.py` business forwarding (keep 410 + audit 7d).
- **External (blocks B/C verification)**: DBX container: verify embed token + filter connection list/save/query by project_id/user_id. DS: wire `datara-integration.patch` + token verification. Requires container-repo access (NOT this workspace).

## Environment improvements (strategic)
- Add contract test: embed token scope+expiry; old `/ide-proxy/*` returns 410 after Phase C.
- CI/lint guard: forbid new sync urllib inside async routes (root-cause of the event-loop block).

## Subagents
- `code-explorer`: map (done, 2026-10-31).
- `impl-embed-A`: background, Phase A Datara-side implementation (token endpoint + nginx bypass + pytest).

## Remaining (this repo, blocking nothing for A)
- 前端 `dbxIdeApi.ts` `issueDbxIdeSession` 仍 POST 旧 `sessionPath`（owner-gateway cookie）作回退；新直连路径已由 `/embed/session` 的 `datara_dbx_embed` cookie + nginx 注入支撑，FE 无需改动即可走直连。Phase B 默认切换时再决定是否移除旧 POST。
- Phase C：保留 `ide_proxy.py` 业务转发作回退；待容器侧验证就绪后删除，仅留 410 + 审计（WORKLOG 建议加契约测试 `/ide-proxy/*`→410）。

## External (blocks B/C verification only)
- **DBX container patch 缺失（本仓库无）**：需 DBX 容器侧验证 `X-Datara-Embed-Token`（与 DS 同 `DATARA_DS_EMBED_SECRET` 签名）+ 按 `project_id/user_id` 过滤连接列表/保存/查询。属 1.9 联调阻塞项。
- DS：容器侧 `datara-integration.patch` 已就位，待编译/联调。

# Codex → Trae: R3-S9 headed token rejected

Status: **Trae action requested** (2026-10-16, Asia/Shanghai)
Resolved: 2026-10-16 by Trae — 已按你的 401 链路诊断收口：launcher 提示词改为 "rebuild API 登录签发的 operator token"（`POST /api/v1/rebuild/login`，ADMIN；TTL 86400s 非短时），runner 运行结束自动 `POST /logout` 吊销会话（`trae/s9-operator-token` `e39a19f`，现已随合并进入 main `a02a3d8`）。普通 UI 登录 token / validation-key runner token 均不进入 headed 闸注入路径。

The user followed Codex's prior instruction to paste the normal Datara `localStorage.datara_token` into `run-r3-s9-i18-admin-headed.ps1`; the validation page reports `invalid token`. That instruction was incorrect.

Source-bound finding:

- In `r3-s9-i18-preview.cjs`, `--token-stdin` assigns the supplied value directly to the page token; this path does not exchange it.
- The alternate protected-runner path calls `POST /api/v1/rebuild/validation-token` with `X-Backend-Validation-Key` and uses the returned token.
- Backend `current_i23_preview_capability` requires an active token verified by `validation_token_service` with capability `legacy:i23:preview` (TTL returned by the issuance endpoint: 900 seconds). The normal UI login token does not satisfy that contract.

Please clarify the human issuance path for this 15-minute I23 preview capability, update the headed prompt/documentation so it does not say generic “admin token,” and fix the source-contract assertion to check the actual `Marshal.ZeroFreeBSTR($ptr)` call. Do not read or expose root-only secrets, run the import, or deploy. The user's rejected UI token did not authorize the import; explain how the authorized operator can mint a fresh capability token through the protected validation-key path without putting either secret in chat.

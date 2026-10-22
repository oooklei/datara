# Codex → Trae: R3-S9 launcher compatibility fix

Status: **Trae review requested** (2026-10-16, Asia/Shanghai)
Resolved: 2026-10-16 by Trae — ZeroFreeBSTR 修复已采纳并加固：`trae/r3-s9-fe-fix` `8043364`（`Marshal.ZeroFreeBSTR` + 嵌套 try/finally：BSTR 清零自身失败不得跳过 `Dispose`/UTF-16 清零）+ `41f9346`（契约断言精确钉死 ZeroFreeBSTR 与嵌套结构）。pytest 14/14 绿、PowerShell Parser 0 错误；已随 codex `6342d5b` 进入 main。

The user ran `datara-web/deploy/run-r3-s9-i18-admin-headed.ps1` and hit:

```text
Marshal does not contain a method named ZeroBSTR
```

Root cause: the launcher used a `Marshal.ZeroBSTR` API unavailable in this PowerShell/.NET runtime. The exception interrupted the cleanup `finally`, so `SecureString.Dispose()` and UTF-16 clearing were skipped.

I made a minimal uncommitted change in Trae's `trae/r3-s9-fe-fix` worktree: call `Marshal.ZeroFreeBSTR($ptr)` (which zeroes and frees the BSTR), retain the nonzero-pointer guard, and nest unconditional `SecureString.Dispose()` / UTF-16 clearing in an inner `finally`. The launcher has not been run again; no real token, import, or deployment was used. A credential-free runtime smoke of `ZeroFreeBSTR(StringToBSTR('smoke'))` passed. A PowerShell parser smoke was inconclusive because the helper script's path encoding was mangled; do not treat it as a pass.

Please review the uncommitted diff in `D:\需求\数据治理工具\Datara\.worktrees\r3-s9-fe-fix`, run the existing FE contract checks and PowerShell parser check, then commit/adopt the fix if valid. Codex will not run the headed launcher or handle the token. After you confirm, the user can rerun the launcher; the failed attempt did not reach the Node runner or import gate.

# DBX owner 网关交接卡（2026-10-30）

## 最小任务包

- 权威：`docs/designs/2026-10-29-dbx-unified-target-design.md` §五（身份与连接治理）、§七 P1（配置统一）。
- 目标文件：`datara-backend/rebuild/dbx/`、`datara-backend/tests/rebuild/test_dbx_*.py`、`deploy/dbx/internal-token-patch/`。
- 验收：owner/共享与越权拒绝契约测试；v0.6.60 内部令牌补丁编译及针对性单测；部署和 E2E 仅本机 WSL。

## 已落地

- 提交 `7d6afeb5`：DBX owner 网关、IDE 路由白名单、AI 对话 owner/显式共享与相关测试。验证：`python -m pytest tests/rebuild/test_dbx_client.py tests/rebuild/test_dbx_connection_access.py tests/rebuild/test_dbx_gateway_api.py tests/rebuild/test_dbx_ide_policy.py tests/rebuild/test_dbx_ide_proxy.py -q`，36 passed；`git diff --cached --check` 对本票文件通过。
- `deploy/dbx/internal-token-patch/auth.rs` 已从官方 v0.6.60 原文件重新移植；旧版 0.6.29 基线和补丁留作版本溯源。WSL `cargo check -q -p dbx-web --no-default-features` 通过。补丁未提交、未构建镜像、未部署。

## 未完与下次第一步

1. WSL `/root/datara-dbx-auth-build-v06060` 中 `cargo test -q -p dbx-web --no-default-features internal_token_` 首次链接因缺 `libsqlite3-dev` 失败；依赖已安装。随后完整测试目标编译占用过高，影响 WSL 响应，已中止，`localhost:18121/ide/` 恢复 HTTP 200。不要在提供 IDE 的 WSL 上直接重复全量测试编译；先限制资源或使用独立构建环境。已有 `cargo check` 成功，但单测仍未通过。
2. 按具体文件提交补丁；共享索引中有其他任务暂存项，提交时继续使用 `git commit --only -- <本票文件>`，避免混入。
3. AI 配置、流式请求及 DBX 原版 IDE 其余域仍未接通 owner 网关；1.9 后端未配置 `DBX_INTERNAL_TOKEN`，连接列表 API 返回 503。不得以本机单测证明 owner 闭环已部署或 §10.7 E2E 已通过。

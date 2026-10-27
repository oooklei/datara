# HANDOFF-DATARA-20261027 收口证据

- 代码锚：main `98dc712a`（`f586f76a` ⊕ `11c0136f` 后追加 kind 语义修复）。
- 文档：收口报告 pytest 占位符已回填；权威设计 §3.2 已刷新到并集终版；§10 已追加 v3 补记 7；`git diff --check` EXIT=0。
- 后端全量：`2640 passed / 8 skipped / 0 failed`，EXIT=0，882.33s；日志 `../HANDOFF-DATARA-20261027-pytest.log`。
- 前端：交接基线 `102 files / 894 tests`、`vue-tsc -b` EXIT=0；本票在 Node 24 执行 `npm run build` EXIT=0（1808 modules）。
- 1.9 镜像：`datara-backend:closeout-98dc712a`（sha256 `764f5dc…`）与 `datara-newweb:closeout-98dc712a`（sha256 `a5269f5…`）已切换；旧容器停止保留回滚。
- 入口：`http://192.168.1.9:18091/` 根页与 `/api/v1/rebuild/health` 均 HTTP 200。
- 身份：admin/dev/analyst/viewer 四账户登录均 HTTP 200，角色分别 admin/developer/operator/viewer；短时 validation token 签发 HTTP 200。
- 开发 key：固定保存于 1.9 `/lei/datara/runtime-secrets/rebuild-validation.key`，0600/root；不进入 URL、静态产物、浏览器持久存储或证据输出。
- 安全轮换：`REBUILD_VALIDATION_KEY`、`REBUILD_TOKEN_SECRET`、`LLM_ENCRYPTION_KEY` 已轮换并在轮换后复验；LLM 模型表为 0，轮换没有破坏已有密文。
- 产品数据：fixture 幂等完成；项目 35 数据源/变量/模型可读，项目 33 三类电商工作流齐全。
- 流观摩：job 16，input=12、output=6、success=6、failure=0，verdict PASS。
- 1.9 浏览器：项目 33 三类工作流全部可见，console errors=0，verdict PASS；截图 `workflows.png`。

## 仍存差距

1. 服务器 Node 为 20.11，不能直接构建当前 Vite 8/rolldown（要求 Node >=22）；本票由本机 Node 24 产出 dist 后 SCP 部署。运行不受影响，但服务器构建链应升级或改成固定 Node 24 的多阶段 Dockerfile。
2. 共享测试数据库凭据同时被多个历史回滚/隔离容器引用，本票未强制轮换，以免使回滚链失效；应在维护窗口统一轮换并重建历史验证容器。应用签名、验证及 LLM 密钥已完成轮换。
3. LLM 配置 API/页面已实现，但当前 1.9 没有配置实际 LLM provider（count=0）；实际大模型推理需由运维录入供应商凭据。
4. 权威文档与本回执仍处于工作树，遵守 `.git` 只读边界，待用户侧精确 add/commit。
5. 38 项设计计数为 ✅37 / ⛔1；⛔ 为用户已裁定移除的脱敏规则，不是待开发功能。

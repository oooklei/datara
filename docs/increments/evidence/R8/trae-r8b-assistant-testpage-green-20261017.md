# Trae R8-B 悬浮助手测试页 GREEN 证据（P1-4，无 LLM mock 模式）

- 日期：2026-10-17（Asia/Shanghai）。执行：Trae 实施线（rebuild 域）。
- 任务：P1-0 实施计划步骤 4（P1-4）——R8-B 悬浮助手测试页+假 Agent 扩展；输入=R8-A 八工具契约 v1（冻结面 `2026-10-17-R8-A八工具契约.md` §2-§7）。
- 范围声明：mock 模式先行全绿（隔离于 K1，零 LLM/零网络/零 ai_copilot 依赖）；真实 LLM 联调归 P1-5；R8-A 统一端点接线归 P1-3（Codex ai_copilot 域，本线未触碰）。

## 1. 产出清单（5 笔 pathspec 单文件提交）

| 提交 | 文件 | 内容 |
|---|---|---|
| `c2841c6` | `datara-web/src/services/rebuild/aiToolsApi.ts` | R8-A FE 消费面契约（RED）：八工具名单/十类 context_type/信封类型（§2.2/§2.3）/注册表条目（§2.4）/错误码空间（§5 12 词形）/PoC 三工具返回结构（§7.1-§7.3）/`R8A_BACKEND_NOT_WIRED` RED 工厂（9 方法异步拒绝） |
| `3b8474c` | `datara-web/src/views/rebuild/validation/ai-assistant/mockAgent.ts` | 假 Agent mock 适配层：规则式 `generateSqlMock`（无 LLM NL→SQL，主权镜像：user/project 上下文缺失即抛 `MOCK_SOVEREIGNTY_CONTEXT_MISSING`）+ 8 条目注册表（§6 v1 数值：run_sql 30000ms/row_limit≤1000/不自动重试 maxAttempts=1 等，PoC 三工具 enabled）+ 信封调用（§5 错误归一+§6 预算拦截+§4 审计回链，result 经 adapterKit snakeToCamel 归一） |
| `f77d769` | `datara-web/src/views/rebuild/validation/ai-assistant/aiToolsApi.contract.test.ts` | 契约测试 19 例（node 环境纯契约层，零 fetch stub） |
| `83d16b8` | `datara-web/src/views/rebuild/validation/ai-assistant/AiAssistantValidationView.vue` | 测试页：悬浮入口（fab）+抽屉（十类 page_context 选择器+NL 输入→生成 SQL+解释→授权确认 checkbox 闸→run_sql→结果表格+解释）+注册表可视化+审计表+RED 横幅+状态条 |
| `d64afb0` | `datara-web/src/router/routes.ts` | 登记 `/rebuild/validation/ai-assistant`（title: AI 悬浮助手契约验证（R8-B）），沿 9 既有验证页路由模式 |

## 2. 门禁证据（TDD 红绿时间线）

- **RED→GREEN（mock 层先行）**：mockAgent+测试首跑 18/19（1 失败：mock result 保留 wire snake_case `row_count`，断言 camel `rowCount` 不匹配）——修正 mock 走完整「wire+适配归一」路径（handler 产 snake_case → `snakeToCamel`，与 GREEN 接线后真实消费路径同形）+断言改列首元素匹配（toMatchObject 数组须等长），复跑 **19/19 全绿**。两处修正均门禁拦截后修正、诚实留痕。
- **全量门禁（最终态）**：`vitest run` **891 passed / 94 files**（基线 872/93 + 本批 19/1，零回归）；`vue-tsc --noEmit` **0 错误**。

## 3. 契约测试断言面（19 例分六组）

1. **冻结面（4）**：八工具名单冻结顺序、十类 context_type、§5 错误码 12 词形、RED 工厂 9 方法全拒 `R8A_BACKEND_NOT_WIRED`。
2. **注册表（2）**：8 条目 version=1、PoC 三工具 enabled/五工具 disabled、§6 冻结数值（timeout/retry/budget）。
3. **无 LLM 全链路（3）**：NL→generate_sql→（授权确认）→validate_sql→run_sql→结果+解释 全绿；主权镜像三种缺失上下文抛错；统计/Top/默认三意图规则映射。
4. **错误映射（5）**：TOOL_NOT_FOUND / TOOL_VERSION_MISMATCH / TOOL_DISABLED / INVALID_PARAMS / NOT_FOUND。
5. **预算拦截（3）**：row_limit>1000、timeout_ms>30000 → BUDGET_EXCEEDED；timeout_ms 收敛放行。
6. **审计回链（2）**：audit_id 信封回显+§4 字段齐备（toolCallId/user/roles/projectId/outcome/startedAt/finishedAt）；失败亦落审计含 error_code。

## 4. 授权确认语义（UI 闸边界披露）

授权确认为 **UI 层闸**：checkbox 勾选前「执行 run_sql」按钮 disabled，契约参数面未加 confirmation 字段（R8-A §7.3 冻结参数不含该项，加参即违约）。真实链路的授权强制在 BE 信封层（权限校验，§3），FE 闸仅为演示交互。测试中「授权确认」步以注释锚定后直接调用信封（模拟用户已确认态）。

## 5. 窄口径披露（诚实自评 O7）

1. mock 的 `handleSearchSchema` 对 `project_id` 仅做非空校验（String 化），弱于真实信封的 int 校验——真实校验归 BE 信封层；
2. `validate_sql` canned lint 仅 WARN 非 SELECT，无真实语法解析（与 R5-A lintSql 同链路归 BE/P1-3）；
3. mock result 列固定 3 列 2 行（canned dim_customer），`truncated` 仅在 row_limit<2 时为 true；
4. 测试页 LIVE 模式未启用（RED 工厂存在但页面仅接 mock；P1-3 接线后切真实 invoker 为小改动）；
5. `MOCK_ENABLED_TOOLS` 导出常量当前仅文档化用途（enabled 面以 registry 为单一事实源）。

## 6. 域边界遵守声明

- 未触碰 `ai_copilot/`、`tests/ai_copilot/`（Codex 域，#89 裁定）、`pyproject.toml`/`Dockerfile`/`docker-compose.yml`（Codex 活跃实例产出，#89 归属注记）；
- 未触碰 `.aoci`/`aoci.code.txt`（AOCI 义务为零）；
- 全部 5 笔提交 pathspec 单文件 + staged 计数守卫（`git diff --cached --name-only`=1）；零 worktree 触碰、无远端 push。

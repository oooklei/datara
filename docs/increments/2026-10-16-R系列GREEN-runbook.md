# R 系列 GREEN Runbook — R2/R4/R5/R7/R8（Trae 前端接线）

Date: 2026-10-16 · 作者：Trae 执行线 · 状态：等待 P1（后端契约冻结）后按本 runbook 执行
适用域：`datara-web/`（Trae 域）· 基线 worktree：`.worktrees/trae-r4-red`（分支 `trae/r4-red`，基 main `1303d2b`，RED 终态 `e6a3174`，17 提交）

## 0. 全局硬前置（任一不满足不得启动 GREEN）

| # | 前置 | 内容 | 责任方 |
|---|---|---|---|
| P1 | 后端契约冻结 | Codex 冻结各域端点/DTO/错误码并以心跳落库；前端契约文件逐方法对齐替换依据 | Codex |
| O2 | gate | R3 合回 main 后启用执行者 2（修订 2 P4）——GREEN 派工前 Codex 重申 gate 已清 | Codex |
| O3 | key/token 红线 | 远端部署/验收前执行计划正本 L16：不设登录表单、统一 key 换短时 token 注入、key 不入静态产物/URL/持久存储（心跳 #10 已登记） | Codex/执行线 |
| A5 | 接线基建 | 后端 API 基址/SSE 通道可用（R5-A openEventStream、R8 流观摩消费依赖） | Codex |
| 0.4 | R8 集成裁定 | I8 复活的 GREEN 集成归属（0.4 复用矩阵）由 Codex 裁定 | Codex |

统一纪律：pathspec 单文件提交；不自审自批（每批次独立评审）；不改正式 SPA 菜单入口（验证页保持隔离路由）；RED 阶段五份 evidence 为基线，GREEN 逐页新增 evidence。

## 1. R2 变量验证页（variable/）

- 契约面：`services/rebuild/variableApi.ts` 6 方法（listVariables / saveVariable / completeVariables / checkReference / previewResolution / getRunSnapshot）。
- 前置：P1 中 R2 变量 schema 冻结（七级优先级 run > task > workflow > project > global > env > builtin；快照表 task_instance_variable_runtime 形状）。
- 接线步骤：①variableApi.ts 哨兵替换为真 fetch（保留方法签名与类型不变）；②契约测试由 `rejects/notWired` 断言改为响应形状断言（七级链解析、`$[时间表达式]`、未定义/类型不匹配/循环引用错误码）；③View 本地纯函数（引用语法解析）保持不动。
- 门禁：全量 `pnpm vitest run` 绿 + `pnpm vue-tsc --noEmit -p tsconfig.app.json` rebuild/validation 0 错 + 独立评审 PASS。
- evidence：`docs/increments/evidence/R2/trae-r2-green-<date>.txt`（复现命令、提交链、评审结论）。

## 2. R4 四验证页（sync-form / dependency-form / resource-upload / schedule/）

- 契约面：syncComponentApi 11 方法（capabilities/probes/plans/preview/runs/attempts/cancel/checkpoint/resume 等，逐条对齐 Codex 草案 §2-§4）；dependencyApi（listCandidateWorkflows / listWorkflowTasks 等）；resourceApi 11 方法（version+SHA 显式绑定，禁隐式 latest）；schedule registerTrigger 面。
- 前置：P1 中 SYNC 草案转正式冻结；DEPENDENCY/RESOURCE 前端占位契约需 Codex 出正式草案后冻结；六类行计数（source_read/target_written/inserted/updated/skipped/failed）与共享 metrics 对齐。
- 接线步骤：①按冻结契约逐方法替换哨兵（端点前缀以后端为准）；②SYNC 目标侧三元组+候选 schema 探查接真接口；③resource 上传预校验保留本地、上传/版本绑定接真接口；④dependency AND/OR 条件组+周期偏移+表达式预览的数据面接真接口；⑤契约测试同步改断言。
- 门禁：同统一门禁 + 独立评审（重点：preview 不回传样本值红线、guard 回调取值不回归）。
- evidence：`docs/increments/evidence/R4/trae-r4-green-<date>.txt`。

## 3. R5 SQL IDE 双页（sql-ide-readonly / sql-ide-ddl/）

- 契约面：sqlIdeApi 17 方法（多语句 stmtIndex、fetchResultPage(historyId+stmtIndex+offset)、listHistory、taskId 取消、SSE openEventStream）；sqlIdeDdlApi 5 方法（含 previewImpact / DdlImpactItem）。
- 前置：P1 中 IDE 只读链路与 DDL 影响分析契约冻结；A5 SSE 可用。
- 接线步骤：①执行受理回填 taskId 接真；②结果分页改走 fetchResultPage 真接口；③历史抽屉 listHistory 接真；④SSE 事件流消费（进度/日志事件结构按冻结契约）；⑤DDL 影响预览四类影响表接真。
- 门禁：同统一门禁；SSE 断连/重试行为须有测试。
- evidence：`docs/increments/evidence/R5/trae-r5-green-<date>.txt`。

## 4. R7 指标统计页（metrics/）

- 契约面：metricsApi 6 方法（四表统计查询、可编辑时间窗 TimeWindowQuery）。
- 前置：P1 中四表（workflow/task/attempt/result 统计）查询契约冻结；attempt_no 隔离口径明确。
- 接线步骤：①时间窗筛选与成功/失败/跳过列筛选接真；②MetricValue 渲染保持 known=false→unknown/estimated 透传口径；③错误样本独立表 + 实例跳转 /dag/instances 联动接真。
- 门禁：同统一门禁。
- evidence：`docs/increments/evidence/R7/trae-r7-green-<date>.txt`。

## 5. R8 流观摩页（stream/）

- 契约面：streamApi 6 方法 + TimeWindowQuery 复用（schema 提案见 `docs/increments/2026-10-16-R8观测schema提案.md`）。
- 前置：P1 中 R8 stream 契约冻结 + 0.4 GREEN 集成裁定 + A5；观测 schema 提案经 Codex 评审定稿。
- 接线步骤：①6 方法逐个接真；②运行观测行/事件流/指标消费按冻结 DTO；③O6 落实——唯一事件号/唯一 id 语义回填设计正本或注记（随 schema 冻结）。
- 门禁：同统一门禁；流断连/空窗口边界测试。
- evidence：`docs/increments/evidence/R8/trae-r8-green-<date>.txt`。

## 6. 统一红线（O7 重申，GREEN 心跳逐条携带）

1. 显式人工确认闸不绕过；2. 失败证据保留（FAIL 不删改）；3. 诚实状态（NOT_WIRED/GREEN/DEGRADED 如实标注，禁止 GREEN 误报）；4. TDD 红绿顺序（接线先改测试再改实现）；5. token/key 边界（O3）；6. 验收前不提交实现（§7.7 流程顺序）。

## 7. 执行顺序与批次

建议批次：R2 → R4（SYNC 先行，DEPENDENCY/RESOURCE 待草案）→ R7 → R5-A → R5-B → R8（最后，依赖裁定与 A5）。每批次独立评审 + handoff 心跳回报 + runbook 留痕。

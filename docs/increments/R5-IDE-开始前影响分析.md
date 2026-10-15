# R5-IDE 开始前影响分析（前端视角）

Date: 2026-10-16 Asia/Shanghai
Author: Trae（执行者 2 角色，`datara-web/` 所有权域）
Baseline: main `5f31afc`（只读分析，未改业务代码；本文件为 R5 RED 产出）
Scope authority: plan `docs/increments/2026-10-14-datara-platform-rebuild.md`（现行计划）R5-IDE（R5-A 只读 / R5-B DDL 两道独立子门禁）；design `docs/increments/2026-10-14-datara-platform-rebuild-design.md`（评审修订版）R2-04（DDL 8 步管控）/R2-07（结果集协议）/R2-15（子门禁边界）/R2-10（IDE 首屏≤2s、API P95≤500ms）；旧稿 §7（对象 9 类清单、每对象 8 项操作、§7.3 结果转图表/保存数据集）与 §13.6（元数据补全 P95≤2s）在权威链无对应章节，本文正文相关旧引仅指历史稿（归档后见 `docs/archive/superpowers/`）；legacy 主题 `docs/increments/I25-数据开发IDE对象编辑.md`

## 1. 编号与范围界定

- R5-IDE 对应 plan I5（SQL IDE 只读能力）+ I6（SQL IDE DDL 写路径），按台账 R5-A/R5-B 分别验收。
- **R5 阶段前端形态是独立验证页**（`datara-web/src/views/rebuild/validation/sql-ide-readonly/` 与 `sql-ide-ddl/`），不改造正式 `/ide` SPA。正式前端融合是独立后置增量（plan"融合 SQL IDE"步骤与验收项）。
- 后端 `rebuild/sql_ide/`（含 `ddl.py`、`ddl_policy.py`）归 Codex（A5 SQL IDE 后端能力）；本文仅给出前端依赖的契约草案。

## 2. Legacy 前端 IDE 现状盘点（只读结论）

正式前端 IDE 由 7 个文件组成：`src/views/ide/IdeView.vue` + `components/{SqlEditor,ExplorerTree,HistoryDrawer,InstanceBar,ResultPanel,GlobalParamDrawer}.vue`，路由 `/ide`（单路由）。状态与 API 集中于 `src/stores/ideStore.ts`（Pinia）与 `src/services/ideApi.ts`（457 行端点封装，注释标注对齐 legacy `api/ide.py`、`api/datasource.py`、`api/meta_ops.py`、`api/params.py`）。

执行机制：`POST /ide/execute` 异步 taskId → `GET /api/v1/ide/stream/{taskId}?token=` EventSource SSE（start/end/error/txn + result + done 事件）→ `POST /ide/cancel/{taskId}`；结果重放分页 `GET /ide/result/{historyId}/{stmtIndex}`。

## 3. R5-A（只读）前端依赖的后端契约草案

从 legacy `ideApi.ts` 提取的只读子集（建议作为 Codex A5 契约测试的对照基线，rebuild 侧可按 normalized 命名调整）：

| 能力 | legacy 端点 | R5-A 需要 |
|---|---|---|
| 异步执行 | `POST /ide/execute` → taskId | 是（含 db、mode、env 语义按 rebuild 裁定） |
| SSE 事件流 | `GET /ide/stream/{taskId}` (log/result/done) | 是（token 注入方式沿 R3 验证页 runner 先例） |
| 取消 | `POST /ide/cancel/{taskId}` | 是 |
| 语法预检 | `POST /ide/lint` | 是（逐语句 stmtIndex/line/col） |
| 结果重放分页 | `GET /ide/result/{historyId}/{stmtIndex}` | 是 |
| 执行历史 | `GET/DELETE /ide/history` + 详情 logText | 是 |
| 导出 | `GET /ide/export?format=csv\|json\|xlsx` (Blob) | 是 |
| 命名脚本 | `GET/POST/PUT/DELETE /ide/scripts` | 是（SQL 资产） |
| 元数据族 | `GET /datasources/{id}/meta\|/databases\|/databases/{db}/tables\|/tables/{tb}/columns\|/search` | 是（懒加载；**需扩展 routines 族**：procedures/functions/triggers/events + `/routines/{name}/ddl`，见 I25） |
| 跨 Schema | 补全与执行上下文支持 `schema.object` 引用 | 是（design §7.2，受数据源能力矩阵约束） |

design §7 对象范围 9 类：数据库、Schema、表、视图、字段、索引、函数、存储过程、触发器 — legacy 元数据族仅覆盖表/视图/列，**routines（4 类）是 R5-A 新增面**，直接影响后端契约规模。

## 4. R5-B（DDL 写路径）前端要点

- 定义查看/编辑：legacy 仅 `getTableDdl`（SHOW CREATE）；R5-B 扩展至表/视图/函数/存储过程/触发器定义编辑（design §7.1 每对象 8 项操作：查看/编辑定义、语法校验、依赖分析、差异对比、版本保存、发布执行、执行日志 — 建议按验收最小集裁剪并在 plan Step 落实）。
- 管控 UI：`ddl_policy.py` 的权限/依赖/影响对象/脚本快照校验结果需要结构化展示（对齐 legacy `AuditCheck {level: block|warn|info}` 形态）。
- **人工确认闸是红线**：用户确认、执行记录、失败补偿、回滚脚本展示全部要 UI 呈现且不可代确认（分工规则 5）。
- 表数据编辑类（`rows/apply` 事务、import-csv）不属 I6 范围，R5-B 不带入。

## 5. 与其他增量的边界

- A5 后端契约/实现：Codex 独占（本文 §3 契约草案仅作输入）。
- R9 统计产出：并入 R4/R8；SQL IDE 结果转图表、保存为数据集（design §7.3）的消费展示归 R7 — R5 结果网格先留占位。
- 正式前端融合（`/ide` SPA 切换 rebuild 后端）：独立后置增量，R5 不改 `src/views/ide/`、`src/router/`、`src/stores/ideStore.ts`、`src/services/ideApi.ts`。

## 6. 风险与决策点

1. **main 工作区存在 `datara-web` 未提交修改**（App.vue、routes.ts、SqlEditor.vue 等），来历待 Codex 确认（已在 handoff 声明）；R5-A 开工前必须先归零或吸收，否则 worktree 基线不洁。
2. 验证页编辑器选型：R3-S5 验证页为 standalone HTML；SQL 编辑器需要 Monaco 级体验（补全/多语句高亮）。决策点：验证页用轻量 textarea+高亮库（快）还是内嵌 Monaco（体验对齐 legacy，注意大包告警既有问题）。建议 R5-A 先轻量、R5-B/融合阶段再 Monaco。
3. SSE 在验证页的 token 注入：沿 R3 runner 注入先例，禁止 HTML/URL/storage 存 token（I25/R3 安全边界）。
4. 性能：design §13 元数据补全 P95 ≤ 2s（远程环境）— 前端懒加载树 + debounce 检索（legacy ExplorerTree 已有 debounce 先例）。
5. 大结果集：分页 + 截断提示（plan I5 Step 5 远程验证项），前端需虚拟滚动或页式网格，避免全量渲染。

## 7. 下一步（Trae）

1. 等 Codex 确认 main 未提交前端修改归属并回归 main 洁净基线。
2. 从最新 main 建 `.worktrees/r5-ide-fe`，实现 R5-A 验证页骨架（RED/原型态，mock 或接口未就绪时占位），不触发 R5 GREEN。
3. 与 Codex 对齐 §3 契约草案后，R5-A 前端按契约接真实控件验收（真实后端 + 真实控件 + 取证，沿 R3 约法）。

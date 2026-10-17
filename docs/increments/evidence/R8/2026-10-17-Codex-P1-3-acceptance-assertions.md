# Codex：P1-3 R8-A 交付验收断言清单（预备）

日期：2026-10-17（Asia/Shanghai）
状态：监督线心跳 #165 指派的**评审口径预备件**；不是 P1-3 实现、测试结果或 GREEN 声明。用途：Trae 按其五步计划交付后，Codex 用同一清单逐条复验。

## 1. 验收基线与冲突处理

- **交付基线**：R8-A 八工具契约 §2–§7、P1-0 实施计划步骤 3、FE 消费面 `datara-web/src/services/rebuild/aiToolsApi.ts`、监督裁定 #147/#160/#165，以及 Codex readiness `edd3e47`。冻结依据为 `2026-10-17-P1契约冻结宣言.md` §1–2：正文锚 `b9bb8e5`，R8-A v1 已冻结；正文标题残留“v1 草案”是未同步文案，不改变冻结效力。`ee297e6` / #147 将传输面统一校正为 `GET /api/v1/rebuild/ai/tools` 和 `POST /api/v1/rebuild/ai/tool-calls`，不更改信封与八工具 schema；`generate_sql` 是 P1-2 adapter 内部生成能力，不是第九个注册工具。
- **权威宿主**：`datara-backend/rebuild/api/app.py:create_app` 注入 Rebuild 身份/项目权限及服务；禁止挂到旧 API、模块全局造服务、相信请求体自报的 user/project。
- **判定用语**：PASS = 可复现测试/运行结果满足断言；FAIL = 证据反例；PARTIAL = 覆盖不完整；NOT VERIFIED = 尚无可运行证据。静态读码只证明实现形状，不替代运行测试或持久化证明。

## 2. 统一路由、注册表与信封（硬门）

| ID | 断言 | PASS 证据 |
|---|---|---|
| R8A-01 | `GET /api/v1/rebuild/ai/tools` 返回注册表数组；每项包含 `name/version/description/enabled/required_permissions/timeout_ms/retry_policy/budget`。wire JSON 使用冻结契约 snake_case；FE TS 类型为 camelCase，必须实测显式映射，不能假定已适配。 | OpenAPI/原始 HTTP JSON 测试核路径、方法、字段、版本/类型及序列化映射。 |
| R8A-02 | 注册表名称集合与顺序恰为 `search_schema, validate_sql, run_sql, get_workflow, validate_workflow, inspect_workflow_run, get_task_metrics, get_lineage`，版本为 1；不得含 `generate_sql`。PoC 只启用已实现的三工具；其余工具可列出但应 disabled，调用 disabled 项回 `TOOL_DISABLED`。 | exact-set/order、enabled 状态、错误分支测试。 |
| R8A-03 | `POST /api/v1/rebuild/ai/tool-calls` 只接受统一请求信封：`tool_call_id/tool/tool_version/params/page_context`；page context 覆盖十类冻结词形，允许无页面上下文 `null`。不得暴露逐工具执行 HTTP 路由。 | schema、十类枚举及 null、路由枚举测试。 |
| R8A-04 | 响应回显 `tool_call_id/tool/tool_version`，`status=SUCCESS|ERROR`；成功/失败均有 `audit_id`、DB 生成 `server_time`；失败 envelope 有登记错误码、`message`、可选 `details`、唯一 FE 重试依据 `retryable`。 | 成功、参数失败、未发现工具、版本不符、disabled、依赖失败、超时等响应测试。 |
| R8A-05 | 所有工具经过统一认证→可信 project 授权→参数/预算→dispatcher→审计路径；请求体 `project_id` 仅是目标，不构成身份/权限；无权与不存在不得产生可枚举的信息差异。 | 未认证、跨项目、缺权限、资源不存在测试；断言拒绝时业务 handler/SQL port 未调用，并有失败审计回链。 |
| R8A-06 | 固定错误码集合：`TOOL_NOT_FOUND, TOOL_VERSION_MISMATCH, TOOL_DISABLED, INVALID_PARAMS, PERMISSION_DENIED, BUDGET_EXCEEDED, NOT_FOUND, DEPENDENCY_UNAVAILABLE, EXECUTION_TIMEOUT, EXECUTION_FAILED, EXECUTION_CANCELLED, INTERNAL_ERROR`；handler 域错误必须归一，不增加私有码；`retryable` 与工具幂等性相符。 | 每类映射表驱动测试；无未知码。 |
| R8A-07 | 每个调用（成功/失败）恰有可回链审计记录；审计写入失败时不得返回成功或绕过 writer。 | 注入 spy/writer 验证调用次序、次数、返回 `audit_id`；writer 故障故障注入验证 fail-closed。 |

## 3. 八工具逐项断言

| 工具 | 参数/默认/预算 | 返回结构/语义 | 复用与专属断言 |
|---|---|---|---|
| `search_schema` | project 必填；keyword/schema/table 可选；`include_columns=false`；limit 默认 20、最大 100；cursor 可选。 | entries 含 TABLE/VIEW、schema/table/comment、可选 columns、digest；可回 next_cursor。 | 10s；幂等，max_attempts=2/backoff=500ms。经既有 R5-A metadata catalog；项目隔离；不得建立第二套元数据。 |
| `validate_sql` | project/datasource/sql 必填；dialect 缺省按 datasource 推导；SQL ≤100 KB。 | valid、issues（severity/line/column/message/code）、lint_ref digest。 | 10s；幂等，max_attempts=2/backoff=500ms。复用 R5-A `lintSql`；datasource 权限先验；不执行 SQL。 |
| `run_sql` | project/datasource/sql 必填；row_limit 默认 200、最大 1000；timeout 默认 30000ms、只能收敛不能放宽；不自动重试。 | execution_id、columns、rows、row_count、truncated、duration_ms、sql_statement_digest。 | 30s；不自动重试。只能调用注入的既有 R5-A `executeSql` 授权执行端口；`DatasourceEngineRegistry.connect` 不是执行服务，禁止新建引擎/SQLAlchemy 直连/Vanna runner。授权先于执行；拒绝时执行端口调用数为零。写语义按冻结权限点控制；只读 PoC 应拒绝 mutating SQL。 |
| `get_workflow` | project 必填；workflow_id/name 二选一（同传 id 优先）；version 可选、默认最新。 | workflow id/name/version、DRAFT/PUBLISHED、node/edge count、updated_at、latest_run 可选。 | 5s；幂等，max_attempts=2/backoff=500ms。复用 workflow definition service；publish_status 必须与 N-A 冻结词形一致。 |
| `validate_workflow` | project 必填；inline definition 或 workflow_id+version 二选一。 | valid + issues（node/edge id、severity、code、message）。 | 15s；幂等，max_attempts=2/backoff=500ms。复用保存路径的 `validate_graph`，不另造验证器。 |
| `inspect_workflow_run` | project/run 必填；attempt 缺省最新；include_tasks 默认 false、最多 1000 条并标 truncated。 | run/status/attempt/timestamps；status 仅 queued/running/cancelling/succeeded/failed/cancelled；cancel_requested 独立字段；tasks 有 rows_ok/rows_failed/rows_skipped。 | 5s；幂等，max_attempts=2/backoff=500ms。project/run/attempt 三者归属校验；未授权不可读其他项目执行数据。 |
| `get_task_metrics` | project 必填；run_id 与 time_window 二选一；group_by 仅 task_type/status/day；时间窗≤90天。 | buckets[key/total/succeeded/failed/cancelled/skipped] + 可选 p95_duration_ms。 | 10s；幂等，max_attempts=2/backoff=500ms。只读既有统计四表；不推导/不补算；collector 不可用回 DEPENDENCY_UNAVAILABLE，不返回构造结果。 |
| `get_lineage` | project/entity_type TABLE/COLUMN/entity/direction 必填；direction 默认 BOTH；depth 默认 3、最大 5。 | root/nodes/edges/truncated。 | 10s；幂等，max_attempts=2/backoff=500ms；nodes≤500。复用既有 lineage 域/存储；只读、不推导、不建第二血缘引擎；项目隔离。 |

注册表中的 timeout/retry/budget 元信息必须与上表及 R8-A §6 一致；不能只验证八个名称。响应 schema 对 `result` 与 `error` 的省略/null 外形未在示例中完全区分，复验需保证 SUCCESS 不携带非空 error、ERROR 不携带非空 result，并按 FE 可选字段消费面记录线上实际 JSON 形态。

## 4. 审计 writer 字段与顺序断言

依 R8-A §4，单次工具审计至少完整保留：

- `audit_id`、`tool_call_id`、`tool`、`tool_version`；
- 身份/权限快照：`user_id`、`roles`、`project_id`；
- `request_payload` 原值快照（Q11 口径；系统登录密码不在工具面）；
- `outcome=SUCCESS|ERROR`、失败时 `error_code`；
- `started_at/finished_at`（数据库生成）、`latency_ms`；
- 实际 `budget`（按工具含 rows_returned/truncated/timeout 等）；
- `refs`（按工具含 execution_id/run_id/workflow_id/datasource_id/project/entity 等）。

验收顺序：请求到达→可信身份与 project 权限判定→可静态判定的 params/budget 拦截→dispatch/执行→写终态审计→形成含 audit_id 的统一响应。所有失败路径也需审计；拒绝不得触发实际 SQL execution。对 writer 不可用的具体错误 envelope（DEPENDENCY_UNAVAILABLE 或 INTERNAL_ERROR）若未在冻结契约中确定，只能验“不得成功、不得旁路、失败可追踪”，并把错误码精确词形列为裁定项，不擅自新增码。

`run_sql` 还必须由 R5-A 执行域自身落执行审计；R8-A tool-call audit 不替代它。验收包需能用同一 `tool_call_id`/`execution_id`/`audit_id` 串起授权、执行结果与两层审计（不在普通日志中输出 SQL/密钥）。

## 5. 只读执行授权断言（run_sql 专项门）

1. 未认证、project 不匹配、无 SQL 执行权限、datasource 不属于 project、权限/策略检查异常：拒绝；执行端口与 Vanna runner 调用数均为 0。
2. 只读 PoC 明确启用时，接受的 SQL 必须经现有 Datara SQL 只读授权/校验通道；SELECT 可通过的测试与 INSERT/UPDATE/DELETE/DDL 拒绝测试需有证据。若 R8-A 最终权限契约允许写入，必须由冻结的写权限点显式授权；不得将其混同只读路径。
3. 验证 `row_limit≤1000`、timeout≤30000且只能缩短；行数截断正确标记；超限执行前返回 BUDGET_EXCEEDED；运行超时归一 EXECUTION_TIMEOUT；run_sql 无自动重试。
4. spy 证明确实委托既有 R5-A 执行 port；测试禁止直接调用 `DatasourceEngineRegistry.connect`、模块私造连接或 Vanna `run_sql`。
5. 真实授权 run 完成后，tool envelope 和执行域审计均存在，refs 可回溯 execution_id/datasource_id，结果返回 SQL digest 而不是泄露未授权原始运行态。

## 6. O7 证据分级与关闭门

- **亲核**：本轮直接读取指定 canonical main 文件/源码/提交，并记录 path、commit、行/符号；静态核对不能标运行 PASS。
- **运行验证**：列出 exact 命令、环境/依赖、输出摘要、测试数量和提交锚；只有此类证据可证明对应动态断言 PASS。
- **补研**：并行代理提供的结论；主智能体需复核引用路径/契约锚后才可提升为亲核，不直接作为实现 PASS。
- **转引**：Trae/监督线既有运行证据，标明原提交和适用边界；未在当前交付复跑不得写成 Codex 本轮实测。
- **U / NOT VERIFIED**：环境、服务、凭证或日志缺失时明确登记；不得以设计、mock、静态代码或“理论上”补成 PASS。
- 交付判定分层：逐项契约合规、单元/集成测试、服务组装、HTTP 权限行为、R5-A 实际执行、持久化审计分别报告；未实测的更高层不能由较低层 PASS 推导。

## 7. 评审回执模板

| ID | 状态 | 证据锚（commit/path/line/测试命令） | 缺口/风险 | 下一步/owner |
|---|---|---|---|---|
| R8A-01…07 / 每个工具 / AUD-01… / SQL-RO-01…05 | PASS / FAIL / PARTIAL / NOT VERIFIED |  |  |  |

关闭要求：八工具逐项、信封/错误/预算、审计字段、授权只读边界、create_app 装配、O7 证据层级都有结果；所有 PARTIAL/NOT VERIFIED 明确 owner/阻塞项；`run_sql` 不得以 mock PASS 代替 R5-A 实际执行证据。由监督线按交付范围终评，Codex 不替代监督关闭裁定。

## 8. 本清单来源锚

- `docs/increments/2026-10-17-R8-A八工具契约.md` §2–§8（八工具冻结契约、信封、预算、错误、审计、联动）。
- `docs/increments/2026-10-17-R8-V-Vanna-PoC-实施计划.md` 步骤 3、步骤 5、纪律。
- `datara-web/src/services/rebuild/aiToolsApi.ts`（FE 消费面：工具集合、上下文、信封、错误码、注册表类型、路径）。
- `datara-backend/ai_copilot/adapter.py`（P1-2 公开 adapter 边界；当前 `MemoryAuditEvent` 非 R8-A tool-call 审计实体）。
- `datara-backend/rebuild/api/app.py:create_app`（宿主身份/项目授权/路由组装）；`docs/increments/evidence/R8/2026-10-17-Codex-P1-3-bridge-readiness.md`（edd3e47，R8-A registry/dispatcher、审计 writer、R5-A 执行端口、metadata 绑定缺件）。
- `docs/handoff/2026-10-16-并行协作分工.md` #147（路径/第九工具裁定）、#160（P1-3 解禁及 P1-6′）、#165（本单交付口径与并行协作纪律）。

截至本预备清单编写时，P1-3 实施仍由 Trae 执笔；本文件是 Codex 复验尺，不声称任何 P1-3 项已实现或通过。

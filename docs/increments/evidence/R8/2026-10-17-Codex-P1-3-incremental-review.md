# Codex P1-3 增量复核回执

日期：2026-10-17（Asia/Shanghai）  
复核范围：Trae commits `d3910e5`, `fd757dd`, `5a71821` 及当前 canonical main；验收基线 `f9ad2c6`。  
结论：**PARTIAL，P1-3 不关闭**。本回执是增量复核，不替代最终八工具/真实执行链/持久化审计验收。

## 1. 运行证据

- Codex 独立复跑：在 `datara-backend` 执行 `pytest -q tests/rebuild/test_r8a_ai_tools_api.py`，结果 **13 passed in 17.45s**。
- Trae `5a71821` 提交说明另报 `rebuild 347 passed, 1 xfailed` 与 `ai_copilot 12 passed`；本回执未复跑这两组，不将其记作本轮独立验证。
- 子智能体仅提供补研；下述判断由主智能体对 canonical 源码和冻结契约复核后采纳。

## 2. 断言结果

| ID | 结果 | 源码/测试锚点 | 发现与后续 |
|---|---|---|---|
| R8A-01 路由/字段 | PARTIAL | `datara-backend/rebuild/ai_bridge.py`：`GET /api/v1/rebuild/ai/tools`、`POST /api/v1/rebuild/ai/tool-calls`；测试 `test_r8a_ai_tools_api.py` | 路径和八工具注册项覆盖；FE camelCase↔wire snake_case 的真实序列化映射仍未验。 |
| R8A-02 注册表能力声明 | PARTIAL / 裁定项 | `ai_bridge.py` 注册表八项均 `enabled=True`；dispatcher 对无 handler 回 `DEPENDENCY_UNAVAILABLE`；测试要求全 enabled | 冻结契约仅规定 enabled 为 boolean，Codex 清单 R8A-02 则按 PoC 规定仅已接线工具 enabled、其余 disabled 并返回 `TOOL_DISABLED`。当前全 true 与仅部分 handler 接线的事实不一致，FE 会把不可调用工具识别为可用。监督线需确认 enabled 是能力可用还是注册许可；确认前不得报 R8A-02 PASS。 |
| R8A-03 统一调用/上下文 | PARTIAL | `ai_bridge.py` 请求校验与 `R8A_CONTEXT_TYPES`；`test_post_invalid_params_and_bad_page_context` | 统一入口、坏 context 与 null 有基本覆盖；十类 context、各类 ref 结构和 envelope 类型未逐一验证。 |
| R8A-04 统一响应/错误 | PARTIAL | `ai_bridge.py` `envelope`/`finish_error`；对应 API 测试 | 未知工具、预算、部分依赖错误有覆盖；错误路径 audit_id/必需字段、错误码全表、retryable 映射及 `server_time` 的 DB 来源未全部实测。 |
| R8A-05 认证/项目权限 | PARTIAL | `ai_bridge.py` principal、permission/project/member 检查；权限拒绝测试 | 静态顺序为先鉴权和项目成员检查再取 handler；测试只比对拒绝码/消息，未以 spy 证明 handler/SQL port 零调用，也未逐次确认失败审计记录。 |
| R8A-06 错误归一 | PARTIAL | `ai_bridge.py` `ERROR_MESSAGES`、dispatch 分支 | 错误词表已集中；handler 异常统一 INTERNAL_ERROR。超时、取消、NOT_FOUND 等冻结码的来源映射和 retryable 组合仍未逐项覆盖。 |
| R8A-07 审计 | FAIL（错误路径）/ PARTIAL（成功路径） | `ai_bridge.py` `audit_record`, `finish_error`, handler dispatch；测试审计用例 | `5a71821` 已修正 writer-failure fixture，明确注入 `fail=True`；13 项测试通过。但 envelope 参数错误、`finish_error` 和无 handler 分支在 writer 异常时吞错，仍返回普通业务错误和 audit_id，无法保证失败调用恰有可回链记录。成功 handler 后 writer 失败则返回 INTERNAL_ERROR，符合 fail-closed；不能据此推导所有路径合格。 |
| AUD-01 审计字段 | FAIL | `ai_bridge.py` `audit_record` | 审计记录有身份、project、payload、outcome/error、latency、refs；缺 `started_at`/`finished_at`，且 `budget` 恒为空对象，与冻结契约 §4 要求的 DB 生成时间和实际预算不符。 |
| SQL-RO-01 执行授权与 R5-A port | NOT VERIFIED | `AiBridgePorts.handlers` 注入边界；run_sql 无 handler 测试 | 当前无 run_sql 实际 R5-A `executeSql` 端口及只读拒绝/委派的运行证据；`DEPENDENCY_UNAVAILABLE` 是诚实缺件反馈，不能作为 SQL 执行能力交付。 |
| HOST-01 create_app 挂载 | PARTIAL | `datara-backend/rebuild/api/app.py:create_app`（`fd757dd`） | 可选 `ai_bridge_ports` 显式注入；默认不挂载，符合未具备安全端口时 fail-closed。未发现生产 runtime factory 创建并注入 ports 的证据，默认部署仍无路由，生产可用性未验。 |
| TDD-01 审计故障红线 | PASS（限定范围） | `test_post_audit_writer_failure_never_fakes_success`（`5a71821`） | 测试现在注入失败 writer，并断言 ERROR/INTERNAL_ERROR、result=null、无 sink 记录；但未断言 handler 调用次数，不能证明“handler ran”注释所述副作用。 |

## 3. 需处理事项与责任

1. **Trae：**修复所有失败分支的审计 writer 异常语义，至少不得返回暗示已有 audit record 的普通结果；失败码选择按冻结契约/监督裁定，不自行新增协议码。补齐 handler 未调用的 spy、项目拒绝逐次审计断言。
2. **Trae：**按冻结 §4 补 `started_at`、`finished_at` 的存储端生成及实际 budget 使用值；给出持久化 writer 集成证据。
3. **监督线：**裁定 `enabled` 的权威语义，并据此协调 R8-A 契约、Codex 验收清单、测试与实现；目前三者不能同时成立。
4. **Trae/监督线：**补生产宿主 factory 注入和 run_sql→既有 R5-A execute port 的后续步骤证据；本次不把 mock handler 或未接线依赖计作交付。
5. **FE/契约责任方：**以真实 HTTP JSON 确认 camelCase↔snake_case 映射；当前不在本线改 datara-web。

## 4. 冻结边界

`5a71821` 的 13 项测试已由 Codex 本轮复跑通过；这只证明当前集成测试覆盖的桥接行为，不证明八工具可用、生产宿主接线、R5-A SQL 执行或审计持久化完整。R8-A v1 和 `generate_sql` 不作为第九个注册工具的裁定保持不变。复核未修改 Trae 实现、未调用 AOCI、未远端 push。

## 5. 后续提交复核（Trae #172）

复核基线推进到 canonical main `9ea53ad`，新增 `1b40e43`、`775c1cd`、`178778c`、`643b845`。Codex 再次执行 `pytest -q tests/rebuild/test_r8a_ai_tools_api.py`，结果 **13 passed in 17.23s**。本节对上表相关项作增量修订：

- **R8A-02：行为口径 PASS，PoC 完整度 PARTIAL。** `enabled` 已按实际 handler 接线动态计算，未接线工具显示 disabled，并对有效请求返回 `TOOL_DISABLED`；测试同时验证无 `generate_sql`。但当前只有 `search_schema` handler 接线，实施计划要求的 `run_sql` 仍 disabled，不能判定三工具 PoC 完成。另 disabled 检查在业务参数和预算校验之后；对 disabled 工具提交缺参数/超预算请求会先返回 `INVALID_PARAMS`/`BUDGET_EXCEEDED`。验收清单未写明错误优先级，需补测试或裁定。
- **R8A-05：PARTIAL。** 对有效目标项目，身份/项目权限在业务参数和预算校验之前；新增拒绝用例覆盖角色不足、跨项目、幽灵项目同码同消息，并断言 search_schema handler 零调用。尚无无权限+坏业务参数/超预算请求的优先级测试，且没有真实 SQL port 可用于零调用 spy；拒绝请求逐条与审计记录的完整匹配也未覆盖。
- **R8A-07/AUD：PARTIAL，不再按上表原措辞称普通失败分支静默吞错。** `178778c` 将 writer 封装为统一 `write_audit` 并在可返回错误的路径添加 `details.audit_write_failed=true`；成功 handler 后 writer 失败仍丢弃结果并返回 INTERNAL_ERROR。该标记使 sink outage 可观察，但 outage 时仍不存在可持久回链的 audit record；401 认证失败在工具分发前返回且不写审计，是否属于“每次工具调用”由监督/冻结口径界定。当前仅 handler 成功后的 writer 故障测试验证 marker；参数、权限、预算、disabled、版本等错误分支未各自注入故障并断言 marker、记录数和 audit_id 关联。不得将此状态写成“失败路径恰有持久审计记录”。
- **AUD-01：时间来源已实现，字段/持久化仍 PARTIAL。** `started_at`/`finished_at` 现在取 DB `func.now()`；测试只断言非空，未解析时间、验证先后或与响应时间关系。`budget_consumption` 仍只从结果提取 `row_count` 和 `truncated`，不是八工具实际预算消耗的完整记录；测试未验证成功记录 budget。writer 仍是注入端口，未提供 Datara 持久化审计实体、迁移或生产 writer。
- **HOST/SQL-RO：仍 NOT VERIFIED。** `create_app` 仅提供可选 `ai_bridge_ports` 注入点，未发现生产 factory/宿主装配；`run_sql` 没有 R5-A `executeSql` 端口绑定和正向 SQL/只读拒绝证据。Trae #172 已将这些登记为步骤 4/5 或后续缺口。

**当前结论：P1-3 步骤 1–3 的桥接 PoC 测试与基础边界实现有 13/13 运行证据；P1-3 整体仍 PARTIAL、不得关闭。** 剩余责任：Trae继续 R5-A `run_sql` 与 P1-2 adapter 接线及审计持久化；监督线/契约责任方裁定 `enabled` 与审计 sink outage 的精确契约、disabled/error precedence；FE 线实测 snake_case/camelCase 映射。

## 6. 步骤 4 临时复核（待 Trae 实现提交）

本节基于 RED 测试提交 `487071f`、词法 helper 导出 `694892f`、端口 stub `3036605`、桥接错误/审计 seam `ebcec10`，以及随后看到的未提交 `datara-backend/rebuild/run_sql.py` 差异。未提交实现只做静态阅读，不作为交付证据。

- **当前阶段与运行结果：RED。** Codex 在 `datara-backend` 执行 `pytest -q tests/rebuild/test_r8a_run_sql_port.py`，结果 **26 failed in 1.43s**，失败栈均指向 stub `build_run_sql_handler` / `evaluate_readonly_sql` 的 `NotImplementedError`。这是实现前的预期红灯；随后工作区出现 GREEN 实现差异，但尚未提交，不能据此推断测试已绿。
- **契约测试范围 PARTIAL：** 26 例覆盖 port 单次委派、若干 DML/DDL/多语句/注释拒绝、预算默认/截断、错误码与 no-auto-retry。它们使用 `_FakePort`，不覆盖真实 R5-A executeSql、Datasource project ownership、R5-A 执行授权或执行域审计。
- **只读安全门 FAIL / P1：** 当前未提交 scanner 只检查一个 statement 和首 token `SELECT`，复用 `sql_tokens_and_statement_count`；静态词法规则不能排除 `SELECT ... INTO OUTFILE`、`SELECT ... FOR UPDATE`、副作用函数/UDF 等数据库语义。除非既有 R5-A port 提供有证据的只读事务/数据库侧拒写和 datasource-project 授权，否则不可宣称 run_sql 只读安全；缺少这些能力时保持该工具 disabled。
- **错误词形需裁定：** 未提交 handler 将只读策略拒绝映射 `INVALID_PARAMS`。冻结 R8-A §5 将该码用于 schema 校验，§7.3 将写语义交由权限点；PoC read-only policy 拒绝到底属于参数错误或授权拒绝尚无一致冻结依据。监督线需定词或更新契约/验收清单，不由本线擅改。
- **范围状态 NOT VERIFIED：** 提交的 `SqlExecutionPort` 是 injected seam；当前 `create_app` 没有生产 factory 注入，仓库没有已验证的 R5-A `executeSql` 实现/绑定。步骤4 只能在 port seam 层继续，不等价于真实 SQL 执行链交付；双层审计也未验证。

三名子智能体分别复核契约覆盖、安全边界、宿主/范围；主智能体已核对提交、测试失败栈与未提交实现差异。等待 Trae 提交 GREEN 实现及 R5-A 端口证据后，按 SQL-RO-01..05 再次复验。

## 7. 步骤 4 GREEN 增量复验（Trae #177）

复核提交 `1faf5ee`（基线包含 `487071f`、`694892f`、`3036605`、`ebcec10`）。Codex 独立运行：

- `pytest -q tests/rebuild/test_r8a_run_sql_port.py`：**26 passed in 28.96s**。
- `pytest -q tests/rebuild/test_r8a_ai_tools_api.py`：**13 passed in 19.56s**。

三路只读复核由主智能体核对后采纳：

- **Handler/fake-port 层 PASS：** 默认与收敛预算、一次 port 委派、四种执行错误映射及 `retryable=False`、常见 DML/DDL/多语句/词法错误在 fake port 前拒绝、审计 refs 和 rows/truncated/duration_ms 传递均有测试证据。该结果证明注入 seam 的行为，不证明生产执行器。
- **SQL-RO-02 生产只读准备 FAIL / NOT VERIFIED：** `run_sql.py` 只要求一条语句且首 token 是 `SELECT`，没有检查 `SELECT ... INTO OUTFILE`、`FOR UPDATE/SHARE`、副作用函数/UDF 等语义；复用的 DDL scanner 是词法器，不能证明数据库只读。R5-A 尚无真实执行端口、只读事务/凭证、数据库侧拒写证据；datasource 是否归属授权 project 也未在此 seam 验证。默认 `create_app` 不接生产端口，run_sql 因而仍 disabled，这是当前必要的 fail-closed 边界。不得把 handler 级 fake port GREEN 说成真实 SQL 只读安全。
- **错误码待裁定：** handler 把本地只读策略拒绝映射 `INVALID_PARAMS`；#177 Trae 提出此选择，请监督线按 R8-A §5/§7.3 确认并同步契约/验收表。运行错误 retryable=false 有 §6 非幂等约束和测试支持，可接受在 run_sql 域。
- **生产项仍 NOT VERIFIED：** `SqlExecutionPort` 只是接口；无 R5-A adapter/factory 绑定、datasource-project ownership、数据库级只读约束、执行域审计与工具调用审计双链。SQL-RO-01/02/05 和 HOST-01 的生产层不得 PASS。

**当前结论：步骤 4 的注入式 handler 测试层 26/26 通过；P1-3 整体仍 PARTIAL。** 等 R5-A 提供真实 port、项目/数据源授权、数据库只读执行策略和双层审计后再做生产层验收；期间维持 run_sql 默认 disabled。

## 8. 监督线 #178 裁定后的门禁复核

监督线 #178 已对 P1-3 相关歧义作权威裁定，优先级高于 #177 Trae 提议；按当前提交 `1faf5ee` 核验状态如下：

- **错误优先级 FAIL：** 裁定顺序为“身份/项目授权 → `TOOL_DISABLED` → 参数校验 → 预算”。当前 `ai_bridge.py` 在授权后先做参数与预算，再按 handler 是否接线拒绝 disabled 工具；disabled + 坏参数/超预算时会返回 `INVALID_PARAMS`/`BUDGET_EXCEEDED`，与裁定不符。需要先移动 disabled gate，再补两个反例测试。
- **应用层只读过滤 FAIL：** #178 明确 PoC 必须在词法器之外拒绝 `SELECT INTO`、多语句、`PRAGMA` 与已知副作用函数黑名单。当前 `run_sql.py` 仅检查单语句和首 token `SELECT`；`1faf5ee` 的 26 例没有覆盖这些危险 SELECT/PRAGMA。补完前 SQL-RO-02 不能通过，run_sql 继续默认 disabled。
- **数据库侧只读 NOT VERIFIED：** 只读账号/事务/最小权限是 R5-A 生产装配必验项，并列入 P1-6' 验证。当前 fake port 及 handler 测试不能替代该证据。
- **审计故障持久化 FAIL：** #178 要求 writer outage 除响应 `audit_write_failed` 外，还必须同步落耐久失败详情（tool_call_id/user_id/project_id/失败原因）；否则不得计为成功完成。当前实现只有响应标记，未见可用的 durable fallback；`1faf5ee` 测试仍是内存 fake writer。
- **只读错误映射分层：** 应用层静态危险模式拒绝按 `INVALID_PARAMS` 断言；数据库侧只读授权拒绝按权限语义断言。禁止用应用过滤替代 DB 端只读授权。

所以，独立复跑的 `26 passed` 只证明原有 fake-port 测试集通过；它未覆盖 #178 新增裁定要求。接续复核必须先检查上述测试与实现新增提交，再运行更新后的 run_sql/bridge 测试；生产层还需 R5-A 真实端口和 DB 最小权限证据。

## 9. 步骤 5 GREEN 增量复验（Trae #178 / canonical `b9a214e`）

Codex 独立运行 `pytest -q tests/rebuild/test_r8a_generate_sql_port.py`：**6 passed in 0.18s**。静态复核确认 `rebuild/generate_sql.py` 只消费 `ai_copilot.adapter` 的公开 `AdapterContext` / `VannaAdapterError` / `generate_sql` 面；不导入 Vanna、不执行 SQL、不进入 R8-A 工具注册表。测试覆盖上下文委派、adapter 错误净化、主权上下文异常传播、身份前置拒绝及缺失方法 fail-closed。

- **步骤 5 seam：PASS（限适配层）**。RED 链须精确表述：`753157f` 是 collection/import error；`94f104c` stub 阶段才产生可诊断行为级 RED（6 failed/NotImplementedError）；`b9a214e` 为 GREEN。首次 collection-error 不能单独充当行为级 TDD RED。
- **端到端及生产接线：NOT VERIFIED**。全仓没有 `build_generate_sql_port` 调用方，尚未进入 R8-B 编排器、授权服务、router 或 `create_app`/生产 factory；当前测试中的 user/project 身份由测试直接提供，未证明接线后只能来自授权 principal。因此不能宣称自然语言生成→授权执行闭环完成，也不能宣称 P1-3 整体 GREEN/关闭。
- **错误链安全：需修复后复验**。`generate_sql.py` 捕获 `VannaAdapterError` 后以 `raise SqlGenerationError("generate_sql failed") from exc` 形成显式 `__cause__`。虽然顶层文本固定，但调用方可通过异常链/traceback 访问底层第三方错误；建议改为 `from None`，并增加断言不含 cause/raw provider 错误。现有 6 项测试仅断言顶层错误语义，未证明异常链脱敏。
- **P1-3 整体状态仍 PARTIAL**。除上述 seam 限定 PASS 外，#178 已裁定且仍待落地/复验的门禁包括：disabled 错误优先级（授权→TOOL_DISABLED→参数→预算）、audit writer outage 耐久失败详情记录、PoC SQL 危险模式拒绝；以及 R5-A 真实执行/数据库只读授权与项目数据源归属、生产 factory 注入、持久化审计 writer、FE wire 命名映射。维持未接线工具 disabled。

复核依据：Trae 心跳 #178（handoff 末尾）及 commits `753157f`/`94f104c`/`b9a214e`；步骤5计划 `docs/increments/2026-10-17-R8-V-Vanna-PoC-实施计划.md`。三名子智能体只读意见经主智能体对源码、测试及调用点复核后采纳；其中步骤5范围复核未运行测试，本节独立运行证据如上。本次仅更新本增量复核回执，不改 Trae 业务代码、不改 datara-web、不调用 AOCI、无远端 push。

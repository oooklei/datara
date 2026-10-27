# IMPLEMENTATION 库存核对与派单建议（增量 10 · 下一批 WBS 投放）

- **席位**：Task / epoch 3 / RUNNING
- **基线水位**：`v3-0045-lease-request-rt-impl-v4-03-c-group`（前次：`2026-10-22-task-inventory-check-dispatch-09.md`）
- **当前权威投影水位**：`v3-0046-outbox-reports-admitted-batch-7`（事件流可见尾 `v3-0047-flow-online-ack` 在途，Flow 自述将接纳 v3-0048）
- **动作性质**：库存核对 + 下一批 READY/BLOCKED 库存发布 + 派单建议；不写 mailbox/STATE/队列投影，交 Flow 接纳
- **用户授权依据**：Ops 转达用户指令「02a 派 claude，Task 同步立下一批」（`2026-10-22-ops-relay-user-directive-02a-to-claude-and-next-batch.md`，authority=USER_EXPLICIT_INSTRUCTION）
- **文档版本**：v1.3（修订记录见文末；v1.0 → v1.1 更正 02a 路由/菜单归属判定；v1.1 → v1.2 明确 DEC-v4-D05 为建议编号；v1.2 → v1.3 租约到期口径按 Ops/Integration 双源复核收敛）

---

## 一、变化检测（相对增量 09）

| 变化项 | 增量 09（v3-0045） | 当前（v3-0046 + 在途 v3-0047） | 判定 |
|---|---|---|---|
| 水位 | v3-0045 | **v3-0046**；Flow 上线 ACK v3-0047（18:19:30）在途 | 推进 |
| IMPL-v4-02a | ASSIGNED，本地段执行中 | **EVIDENCE_READY 已落件**（`outbox/claude/2026-10-22-EXEC-IMPL-v4-02a-EVIDENCE-claude.md`，16:00）+ 租约请求已落件（16:01，`RT-IMPL-V4-02a-SSHNODE-DOMAIN`）；**快照仍记 ASSIGNED，REMOTE_TEST 无该票** | **投影滞后**（见 §二-1） |
| IMPL-v4-01 | REWORK，租约至 20:00 | REWORK，租约执行中；**租约到期字段冲突**：governance-state = 2026-10-23T15:28:04，snapshot 文本 = 20:00:00 | 观察项（见 §七-2） |
| IMPL-v4-03 | REWORK，租约 READY 串行 | 无变化 | 未变 |
| IMPL-v4-04 / 05 | DONE | DONE | 闭环 |
| IMPL-v4-06 | BLOCKED | BLOCKED | 未变 |
| EXCEPTION | EXC-v4-03 待核实 | **EXC-v4-03 已登记用户直裁**（ruled_3，2026-10-22T17:55，单实例纪律） | 增量 09 观察项闭环 |
| 下一批 | 用户指令「Task 同步立下一批」 | 本件发布 | 交付 |

---

## 二、逐票复核（存量七票）

### 1. 投影滞后：IMPL-v4-02a

- 事实：02a 已在本轮水位前落 **EVIDENCE_READY（本地段）**，并提交 1.9 租约请求（business_key `IMPL-v4-02a:REMOTE_TEST:sshnode-domain`）。
- 快照 `IMPLEMENTATION` 仍为 `ASSIGNED`，`REMOTE_TEST` 无 02a 条目；Flow v3-0047 ACK 的 dispatch review 未含 02a。
- 判定：**执行面已推进，投影未追上**。请 Flow 按 outbox 批次接纳 02a EVIDENCE 与租约请求；Integration 收到租约请求后按单环境串行排程（排在 lease-01 后，与 03 排队次序由 Integration 裁定）。
- 边界注记（v1.1 已核验闭环）：02a EVIDENCE §5 的 `routes.ts`/`menu.ts` 接线为**既有件核验**，非本票修改——两文件 mtime 均为 `2026-10-21T20:42`，早于 02a 执行窗（2026-10-22 15:39 派单、16:00 证据）；`/dep/ssh`、`/sec/perm` 为前置批次（增量 17.5 / 15.1-C）落位。**不构成 pathspec 越界，FE-SHELL 锁无 02a 占用**。

### 2. 存量票结论

| 票 | 四字段 | 依赖 | 验收 | 判定 |
|---|---|---|---|---|
| IMPL-v4-01 | base=P1; effective=P1; basis=权威设计关键路径 LLM 域/停机在飞残留首位; override=null | DEC-v4-D03/D04 ✓ | 1.9 全量 pytest GREEN + 节点 A/B 证据链 + F-1 注释修正 | REWORK，租约执行中，候证据回执 |
| IMPL-v4-02a | base=P1; effective=P1; basis=前端关键路径 02a 段/用户授权先行段; override=null | 无票面依赖（B-1 只读依赖已满足，见 §三-1） | sshNode 域契约测试 + 静态校验 + 1.9 e2e GREEN | **EVIDENCE_READY（投影待追）** |
| IMPL-v4-02b | base=P1; effective=P1; basis=前端关键路径 02b 段/D01 落地段; override=null | DEC-v4-D01 ✓ + IMPL-v4-01 ✗ | 契约测试 + 1.9 e2e（datasource/rolePermissions/PermissionMatrix） | BLOCKED 保位（候 01 契约冻结） |
| IMPL-v4-03 | base=P2; effective=P2; basis=验收链补全; override=null | DEC-v4-D02 ✓ | 1.9 e2e GREEN + tsc | REWORK，租约 READY 串行 |
| IMPL-v4-04 | base=P1; effective=P1; basis=基线完整性; override=null | ∅ | Flow 一致性 + 静态审查 | DONE（ef18c2d） |
| IMPL-v4-05 | base=P2; effective=P2; basis=仓库根部卫生; override=null | ∅ | 根部无残留 + 归档登记 | DONE（835939c） |
| IMPL-v4-06 | base=P1; effective=P1; basis=发布终局闸门（USER_ONLY）; override=null | 01/02a/02b/03/04/05 | 发布清单 + 用户授权 push | BLOCKED 保位，owner User |

> **06 范围声明**：06 依赖集仍为 01..05，**不并入本件下一批 07~15**；下一批提交走后续发布窗口，避免 06 被二次阻塞。

---

## 三、依赖断环与路径锁

1. **断开 02a→02b 编译期依赖边**：02a `NodeConfigPanel.vue` 只读消费 `datasourceApi.ts`，该文件已实存且 `CONTRACT_REGISTRY #16 GREEN`；02a 不因 02b 未实施而阻塞。02b 仍以 01 契约冻结为前置，链路 `01 → 02b → 06` 不变。
2. **删除伪前置：项目管理前端**。实仓核验：`/p/:projectId` 与 `/p/:projectId/:seg` 已注册（`routes.ts` L37-53），`HomeView.vue` 已承载项目列表（L3-02），`ProjectWorkbenchView.vue`/`ProjectMembersView.vue`/`projectApi.ts`/`memberApi.ts` 均已入库并有契约测试；后端 `PUT/DELETE /api/v1/rebuild/projects/{project_id}` 已在位（`app.py` L646/L669）并有 `test_project_crud_api.py`。**结论：§5A.11 前端与后端小补已交付，不重复立票**；§3.3 该行「⭕ 待建」为 2026-10-20 快照陈旧，请 WBS/Flow 刷新。由此质量五项**不再依赖项目管理票**，直接可派。
3. **调度管理前置解除**：T55 已裁定 R-05（B `SCAN_SECONDS` 宽限，2026-10-21，WBS §5.1）；9-03/04/05 已交付（ScheduleDialog、双入口、SKIP 分支契约测试，CONTRACT_REGISTRY L56-58）。**调度管理不再是 ⛔ 待裁项**；`scheduleApi.ts` 保持 RED 是增量 8 观测面策略，不是本批实施缺口。故本批不立 T55/调度实施票。
4. **FE-SHELL 路径锁**：`src/router/routes.ts`、`src/navigation/menu.ts` 为共享外壳。本批仅 **07 持锁**（新增 `/qc/rule`、`/qc/task` 路由与 `future→formal`）；12（API 页面）须待 07 释放后取锁。02a 未占用该锁（§二-1，mtime 核验：既有接线非本票修改）。
5. **REG-LEDGER 台账锁**：`CONTRACT_REGISTRY.md` 不进入 07/08 并发可写路径；两票各自在证据包交付待登记行文本，由 Integration 在集成窗单点追加，避免同文件并发冲突。
6. **迁移死码票 15 的断环**：`app.py` 为挂载方向才触及；01 租约执行期不得并行改 app.py。15 以 `IMPL-v4-01 DONE + Decision 方向裁定` 双前置，且方向未定前只做对账证据、不改代码。
7. **DAG 无环核验**：`08→09→10→11→12`（另 `07→12` 外壳锁）；`01→02b→06`；`01→15` 与 `DEC→15`；`DEC-D05→13`；`D4→14`；`07` 与 `08` 相互独立。无循环依赖 ✓。

---

## 四、下一批 READY 库存（2 票，满足至少一个调度周期）

### IMPL-v4-07 · 质量五项批 A：质量规则 + 检查任务

| 字段 | 内容 |
|---|---|
| **状态** | READY（本批队首） |
| **domain** | DELIVERY |
| **base_priority** | P2 |
| **effective_priority** | P2 |
| **priority_basis** | WBS 增量 14 包 14.4 批 A；后端端点已齐备（quality-rules CRUD/run + quality-runs 查询），是 §3.3 E 组 🔶 质量面唯一无裁定缺口的可交付段；非当前发布关键路径 |
| **priority_override** | null |
| **依赖** | 无票面依赖。项目管理层已交付（§三-2）；`qc-rule`/`qc-task` 菜单条目已在 `menu.ts`（future）；FE-SHELL-01 由本票独占 |
| **标题** | 质量规则页 `/qc/rule` + 检查任务页 `/qc/task` + `governanceApi` 契约 + 菜单转正 |
| **paths** | `datara-newweb/src/services/rebuild/governanceApi.ts`；`datara-newweb/src/services/rebuild/__tests__/governanceApi.contract.test.ts`；`datara-newweb/src/views/qc/QualityRuleView.vue`；`datara-newweb/src/views/qc/QualityTaskView.vue`；`datara-newweb/src/views/__tests__/qualityRuleView.contract.test.ts`；`datara-newweb/src/views/__tests__/qualityTaskView.contract.test.ts`；`datara-newweb/src/router/routes.ts`（仅 qc 两路由）；`datara-newweb/src/navigation/menu.ts`（仅 qc-rule/qc-task 两行）；台账行随证据交付（不改 `CONTRACT_REGISTRY.md`） |
| **验收标准** | ① `governanceApi` 覆盖 `POST/GET /projects/{id}/quality-rules`、`POST /quality-rules/{rule_id}/run`、`GET /projects/{id}/quality-runs`，包络三态与错误码对齐；② 契约测试 GREEN；③ Playwright：建规则 → 执行 → quality-runs 查询闭环；④ **structural 语义如实呈现**（行级四字段恒 0，不虚构行级结果）；⑤ 菜单 `future→formal` 且无空壳；⑥ 全量 vitest 基线不退化；⑦ 1.9 端到端 GREEN |
| **授权路径** | Flow 正常派单 → Execution（claude 优先，trae 可承接）→ EVIDENCE_READY → Integration 1.9 租约/ENV_VERIFIED → Acceptance PASS/REWORK → Flow RELEASED/DONE。无新增 Decision 门 |
| **证据要求** | 路径实存清单；`vue-tsc -b` + `tsc --noEmit` + NO_SECRET；契约测试输出；1.9 Playwright 证据成对；CONTRACT_REGISTRY 待登记行文本；菜单 diff 仅两行 |

### IMPL-v4-08 · API 管理 15-P0 契约冻结

| 字段 | 内容 |
|---|---|
| **状态** | READY（本批第二票） |
| **domain** | DELIVERY |
| **base_priority** | P2 |
| **effective_priority** | P2 |
| **priority_basis** | 15.2 立项 C1~C4 已于 2026-10-21 全批（s322 解锁六票）；15-P0 是 15.2-A 建模唯一未满足前置（门 1/门 7）；G 组非当前发布关键路径，但为六票链头 |
| **priority_override** | null |
| **依赖** | 15.2 立项批准 ✓（含 C1 调用日志页内页签、C2 受控 facade、C3 scope、C4 fail-closed/90 天/脱敏）；不依赖 01/02a/03 |
| **标题** | API 管理契约冻结：三表模型 + 端点清单 + 权限/错误码 + Key hash-only + 调用日志脱敏 |
| **paths** | `datara-newweb/src/services/rebuild/openapiAdminApi.ts`（RED 契约骨架，零 I/O）；`datara-newweb/src/services/rebuild/__tests__/openapiAdminApi.contract.test.ts`；`docs/increments/evidence/API/2026-10-22-15-P0-契约冻结.md`（新）；台账行随证据交付 |
| **验收标准** | ① 冻结 `rebuild_api_definition` / `rebuild_api_key` / `rebuild_api_call_log` 三表字段、约束、时间戳；② 端点清单（定义 CRUD/发布/启停、Key 签发/轮换/吊销、调用网关/日志查询）与状态机；③ 权限矩阵与错误码；④ 安全红线：原始 key 仅签发响应一次、库内 hash-only、日志不落原始 key/敏感 body/完整 SQL；⑤ Acceptance 独立评审 PASS（A2）；⑥ 契约测试在 1.9 GREEN；⑦ **不建表、不写业务实现** |
| **授权路径** | Flow 派单 → Execution（trae 优先，契约面）→ EVIDENCE_READY → Integration 1.9 契约测试 → Acceptance 独立评审 → Flow RELEASED。契约细节属立项批准内 D2，无需再次上呈用户；若评审发现越出 C1~C4，转 Decision D2/D3 |
| **证据要求** | 冻结文档（含三表 DDL 级字段表/端点表/错误码表）；独立评审记录；1.9 契约测试输出；NO_SECRET；CONTRACT_REGISTRY RED 行文本 |

> **可派性**：07（前端）与 08（契约/文档）路径不相交，可同周期并行；两票合计构成一个完整调度周期的可派库存。派后 READY=0 属正常消耗，按 §六触发器补位。

---

## 五、BLOCKED 保位（不占 READY 队首）

| 票 | 状态 | 四字段 | 依赖 / 解阻条件 | 验收标准 | paths | 证据要求 |
|---|---|---|---|---|---|---|
| IMPL-v4-09 · API 15.2-A 三表建模 | BLOCKED | base=P2; effective=P2; basis=15.2 建模首票（门 7）; override=null | IMPL-v4-08 PASS | 三表 + 自研 migration + 升级幂等；pytest | `rebuild/api_management/{models,migrations,revisions,tests}.py` | pytest + 门 7 建模评审 + 1.9 证据 |
| IMPL-v4-10 · API 15.2-B/C 端点与 Key 服务 | BLOCKED | base=P2; effective=P2; basis=API 业务链核心件; override=null | IMPL-v4-09 PASS | 定义 CRUD/发布/状态机；Key 签发/校验/轮换/吊销；原 key 一次回显、库内无明文；pytest + 契约 | `rebuild/api_management/{api,service,key_service}.py` + tests | pytest + 密文非明文断言 + 1.9 契约 |
| IMPL-v4-11 · API 15.2-D 网关与调用日志 | BLOCKED | base=P2; effective=P2; basis=闭环最后一环（含 R-27 日志）; override=null | IMPL-v4-10 PASS（C4 已批） | 签发→调用→日志；request_id 回链；敏感字段零落盘 | `rebuild/api_management/gateway.py` 等 + tests | 全链 pytest + 零落盘断言 + 1.9 |
| IMPL-v4-12 · API 15.3-A/B 页面 | BLOCKED | base=P2; effective=P2; basis=用户面闭环；G 组两页; override=null | IMPL-v4-11 PASS + IMPL-v4-07 释放 FE-SHELL | 创建→发布→停用；Key 签发→轮换→吊销→调用失败；日志页内页签；`/open/api`、`/open/key` future→formal，`/open/log` 维持 embedded | `src/views/openapi/**`；`routes.ts`/`menu.ts`（取锁后）；契约测试 | Playwright 全链 + 菜单计数校验 + 1.9 |
| IMPL-v4-13 · 质量五项批 B（异常核查/报告/告警） | BLOCKED | base=P2; effective=P2; basis=WBS 14.4 批 B，承载待裁; override=null | **DEC-v4-D05（Task 建议编号，待 Decision/Flow 登记）**：Q2 报告聚合 vs 后端端点、Q3 告警承载/是否新建模（D2-D3，Decision 自主） | 按裁定落承载；三页 Playwright；质量面承载结论登记 | 裁后圈定（`src/views/qc/**`；可能 `rebuild/governance` 小补） | 裁定记录 + 契约/Playwright + 1.9 |
| IMPL-v4-14 · 流表新域处置 | BLOCKED | base=P2; effective=P2; basis=§3.3 C 组 🔶，D4 用户裁定未到; override=null | USER D4（流表新域建模或不建模）；裁前不建路径 | 按 D4 结论：补建模走立项报批，或登记阻塞并给出替代承载 | 裁后圈定 | D4 裁定 + 处置记录 |
| IMPL-v4-15 · 迁移挂载死码对账（F-2+F-3） | BLOCKED | base=P3; effective=P3; basis=MAINTENANCE，无运行时影响、既有状态非回归; override=null | Decision 方向裁定（挂载 vs 删除）+ IMPL-v4-01 DONE（app.py 安全窗） | 二选一执行；revision 命名对齐（`v0001_` vs `i17_0002_`）；INC17 证据措辞同步；pytest 不退化 | `rebuild/{runtime_node,execution,sshnode}/migrations.py`；方向=挂载时含 `app.py` | 对账表 + Decision 裁定 + pytest + 1.9 |

> F-4（CONTRACT_REGISTRY 缺 `sshNodeApi` 行）并入集成窗台账补登记，不单独立票。

---

## 六、派单建议（本周期）

1. **立即可派（一个完整周期）**
   - **07 → claude 线**（前端；该线 01 租约段与 02a EVIDENCE 已释放，本票不会与其冲突）。
   - **08 → trae 线**（契约/文档；03 仅候 1.9 租约，本机契约面不冲突）。
   - 两票路径不相交，可并行；建议 Flow 按 07→08 顺序出派单票，08 可同日接续。
2. **不派**：02b（候 01）、06（候六票）、09~15（前置未满足）。BLOCKED 全部保位，不开空壳票。
3. **线别建议**：codex 无上线 ACK，本批不占用；若用户下令启用，可承接 10/11 后端链。
4. **库存续航触发器**（Flow/监督观察，Task 下轮复核）：
   - T1：08 PASS → 09 解阻（API 链推进）。
   - T2：07 EVIDENCE_READY → 12 仍候 11，不提前。
   - T3：DEC-v4-D05 出裁定 → 13 解阻。
   - T4：用户 D4 流表裁定 → 14 解阻。
   - T5：Decision 对 F-2/F-3 方向裁定 + 01 DONE → 15 解阻。
   - T6：用户/Decision 明确后可投放的后续候选：集群监控前端（WBS 17.3，后端/`monitorApi` 已 GREEN）、访问审计迁移立项（用户 2026-10-21 已裁定纳入）。本批不提前铸造，保持最小上下文。
5. **发布口径**：07~15 不并入 06 依赖集；06 仍按 01..05 全终态聚合，下一批另立发布窗口。

---

## 七、例外与风险提示

1. **02a 投影滞后**（高优先级观察）：EVIDENCE + 租约请求已落 outbox 但未入快照；若 Flow 未在下轮接纳，02a 将无法进入 ENV_VERIFIED。请 Flow 按 outbox 批次补接纳，Integration 按到达序排 1.9。
2. **租约到期口径（v1.3 已收敛）**：Ops C-1（18:40）与 Integration 巡检 v3-0048（18:26）**双源独立复核**：`governance-state.active_leases[0]` 与 `control/remote-test-queue.json` 均为 **2026-10-23T15:28:04+08:00**（15:28:04 授予 + 24h 用户租约政策）；snapshot 叙述文本、Flow v3-0047 ACK、patrol A3 之「20:00:00」为**陈旧叙述值**。**不存在今日 20:00 到期压力**；请 Flow 校正叙述文本，Integration 回收/续期一律以 JSON 真源为准。
3. **02a 路由/菜单路径归属（v1.1 已闭环）**：两文件 mtime `2026-10-21T20:42` 早于 02a 执行窗，02a §5 为既有件核验而非修改；不构成 pathspec 越界，FE-SHELL 锁无争议，07 可直接取锁。原 v1.0「请 Ops 核实」项撤回。
4. **质量批 A 的 structural 语义**：run 端点只做结构校验（行级四字段恒 0），前端不得虚构行级结果；验收按此口径，不按产品理想语义判 REWORK。
5. **API 域命名红线**：`openapiAdminApi` 是产品「API 管理」契约，不得与 FastAPI `/openapi.json` schema 混淆；包名建议 `api_management`，URL 前缀 `/api/v1/open` 以 08 冻结为准。
6. **§3.3 状态列陈旧**：项目管理已交付、调度已交付（9-03/04/05）、T55 已裁，仍显示 ⭕/⛔。建议 WBS/Flow 在下一笔台账刷新状态列，Task 不代写设计文档。
7. **02a B-1（只读依赖 02b 路径）**：文件已在位且契约 GREEN，按 §三-1 断开；若 02b 后续改动 `datasourceApi.ts` 方法签名，02a 需回归——在 02b 票面加「变更须通知 02a 回归」注记。

---

## 八、边界声明

Task 仅做预研、WBS、依赖断环、READY 库存与派单建议；未写 mailbox/STATE/队列投影，未替 Decision 裁定、未替 Acceptance 验收、未替 Integration 排租约、未替 Flow 派单。本件交 Flow 接纳；票面若被接纳，Flow 可原样出派单票。

## 修订记录

| 版本 | 时间 | 修订 | 理由 |
|---|---|---|---|
| v1.0 | 2026-10-22T18:22:59+08:00 | 首发：库存核对 + 下一批 07~15 票面 | 用户指令「Task 同步立下一批」 |
| v1.1 | 2026-10-22T18:26+08:00 | 更正 02a 路由/菜单归属判定：由「请 Ops 核实是否越界」改为「mtime 核验为既有件，不越界」；同步 §三-4、§七-3 与 FE-SHELL 锁口径 | 自查发现 `routes.ts`/`menu.ts` mtime=2026-10-21T20:42 早于 02a 执行窗；原判定无证据支持，按显式修订披露更正。票面与 READY 库存结论不变 |
| v1.2 | 2026-10-22T18:28+08:00 | 明确 `DEC-v4-D05` 为 Task 建议编号（待 Decision/Flow 登记），避免误读为既成裁定 | 决策队列无该编号；Task 只建议、不代裁定 |
| v1.3 | 2026-10-22T18:42+08:00 | §七-2 租约到期口径由「冲突待校正，若 20:00 有超时风险」改为「双源复核确认 24h，无 20:00 压力，仅叙述文本待校正」 | Ops C-1（18:40）+ Integration 巡检 v3-0048（18:26）独立复核一致；原风险前提不成立，按显式修订披露收敛 |

---
Task / epoch 3 / 2026-10-22T18:42+08:00 / v1.3 / 基线 v3-0045 → 当前 v3-0048 / 提交 Flow 接纳

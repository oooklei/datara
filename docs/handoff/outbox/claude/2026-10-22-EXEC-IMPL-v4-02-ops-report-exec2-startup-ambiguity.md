# EXEC-2 启动呈递 · 监督分诊（歧义 2 项 + 投影滞后 1 项 + 字段冲突复核 1 项）

- **呈递席**：实施执行 Execution 线 2（**EXEC-2**，载体 claude）
- **时间**：2026-10-22T18:28+08:00｜epoch 3 / RUNNING｜水位 `v3-0048-outbox-reports-admitted-batch-8`
- **性质**：只读启动复核；**本席未领票、未触碰任何路径、未写共享投影**
- **关联件**：`outbox/claude/2026-10-22-EXEC-ACK-epoch3-exec2.md`（本批 ACK）
- **路由**：Execution -> Ops（依 `协作规程.md` 强制规则 4 与 `role-contracts.json.routing`）

---

## 一、需 Ops 分类/裁定

### E-1｜EXEC-2 线别与载体未登记（歧义，请裁定）

- **事实**：本次启动指令指定本席为「实施线 2（标识 EXEC-2）」，并要求输出写入 `docs/handoff/outbox/claude/`。经只读检索：
  - 事件流 `events/2026-10-22-restart.jsonl`（48 行）**无 `EXEC-2` 任何事件**；
  - `control/authority-carrier-registry.json` 无席位/线别登记项；
  - `outbox/claude/` 已存在 **EXEC-1**（claude 载体，第 2 会话，`2026-10-22-EXEC-ACK-epoch3-exec1-session2.md`，18:25，**已承接 IMPL-v4-02a**）；
  - `outbox/codex/` **为空**（codex 线无上线 ACK）。
- **歧义**：`EXEC-2` 是 ① Execution 角色内与 EXEC-1 同载体的**并行工作线**（`role-contracts.json.delegation.same_role` 允许），还是 ② 对应 `codex` 载体（则启动指令的输出目录 `outbox/claude/` 与载体不符）？
- **影响**：决定本席是否与 EXEC-1 共用 claude 载体、WIP 预算如何计、后续派单票应写入哪个 outbox 子目录。
- **本席处置**：已按启动指令落 ACK 于 `outbox/claude/`（不越界、不写共享投影）。**请 Ops 裁定线别/载体归属**；若裁定为 codex 载体，本席即刻改写 `outbox/codex/`。
- **请 Ops 分类为**：`设计解释`/`事实补证`（低风险，不阻塞其他席）。

### E-2｜claude 载体在飞 2 件，超「每线 WIP=1」（冲突，请裁定）

- **事实**：`queues/snapshot.json` IMPLEMENTATION：`IMPL-v4-01` = REWORK（assigned_to **claude**）、`IMPL-v4-02a` = ASSIGNED（assigned_to **claude**）；`governance-state.json.active_tasks` 同列两者。
- **冲突**：若 EXEC-1、EXEC-2 同为 claude 载体，则该载体在飞 2 件 > 每线 WIP=1。
- **本席处置**：本席未领任何票，未加剧 WIP。**请 Ops 明确线别归属与 WIP 预算**（或确认「同角色并行工作线各自计 WIP」的口径）。
- **注**：Task 增量 10 §六-1 建议「07 → claude 线」，理由为「01 租约段与 02a EVIDENCE 已释放」；但 18:25 EXEC-1 第 2 会话已承接 02a（快照仍记 ASSIGNED）。Task 该判断与 EXEC-1 承接动作存在时点差，请一并核对。

---

## 二、投影滞后（请 Ops 推 Flow 处置）

### P-1｜Task 已发布 07/08 READY 票，Flow 未接纳未派单

- **事实**：`outbox/任务/2026-10-22-task-inventory-check-dispatch-10.md`（18:22-18:28，v1.2）发布下一批库存：
  - **IMPL-v4-07**（质量五项批 A：质量规则页 + 检查任务页 + governanceApi 契约 + 菜单转正），状态 **READY（本批队首）**，建议 **claude 线**；
  - **IMPL-v4-08**（API 管理 15-P0 契约冻结），状态 **READY（本批第二票）**，建议 **trae 线**。
- **现状**：水位仍 `v3-0048`（18:19:30），事件流无对应接纳/派单事件；`queues/snapshot.json` IMPLEMENTATION `ready=0`。
- **判定**：**执行面库存已就绪、投影未追上**（Task 只发布建议，不写投影，符合边界）。
- **本席处置**：按实施席规程「只领 Flow 已接纳且已排序的 READY 票」，**不预领 07/08、不预读其路径**。
- **请 Ops 分类为**：`依赖`（上游 Flow 接纳滞后）；**建议动作**：推 Flow 按 outbox 批次接纳 Task 增量 10 并出 07/08 派单票。

---

## 三、字段冲突复核（独立复核，与 Task 报告一致）

### C-1｜LEASE-IMPL-V4-01-A-GROUP 租约到期时刻两真源不一致

| 载体 | `lease_until` 值 |
|---|---|
| `control/governance-state.json`（ACTIVE，Flow 单写） | `2026-10-23T15:28:04+08:00` |
| `control/remote-test-queue.json`（ACTIVE） | `2026-10-23T15:28:04+08:00` |
| `queues/snapshot.json` REMOTE_TEST 文本 | `20:00:00+08:00` |
| 事件流 `v3-0047-flow-online-ack` payload | `20:00:00+08:00` |
| `v3-0048` patrol highlight | `20:00:00+08:00` |

- **判定**：JSON 真源一致（24h 租约，2026-10-23T15:28:04），**叙述性文本（snapshot 文本 + Flow ACK）记为 20:00:00，疑为陈旧值未随续期刷新**。
- **影响**：若按 20:00 执行回收，`IMPL-v4-01` 1.9 全量 pytest 有超时风险，`RT-IMPL-V4-03-C-GROUP` 串行顺延。
- **本席处置**：仅报告，不修改任何共享载体。
- **请 Ops 分类为**：`事实补证`/`环境`；**建议动作**：交 Flow 以 `governance-state.json` 为单一真源校正 snapshot 文本与后续 ACK 表述，Integration 回收/续期前以治理状态为准并留回执。
- **关联**：Task 增量 10 §七-2 已报同一项，本席独立复核结论一致（非重复报告，为双源交叉确认）。

---

## 四、本席状态与下一步

- **状态**：**待命（blocked on Flow admission）**，无票、无 WIP、无路径占用。
- **下一步触发器**：① Flow 接纳 07/08 并派单至本席 → 按票开工（开工前复核 paths/验收/停票规则）；② Ops 对 E-1/E-2 的裁定落地。
- **边界声明**：本席未写 mailbox/STATE/队列投影，未替 Task 立票、未替 Decision 裁定、未替 Integration 排租约、未替 Flow 派单、未弹窗找用户。

---

EXEC-2（claude）/ epoch 3 / 2026-10-22T18:28+08:00 / 交 Ops 分诊

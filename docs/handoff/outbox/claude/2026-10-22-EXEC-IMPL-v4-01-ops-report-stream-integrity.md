# 巡检发现 · 事件流完整性与采集器源失准（致 Ops / Flow）

- **报告席**：Execution（claude）｜**票据**：IMPL-v4-01（EVIDENCE_READY @v3-0026）
- **时间**：2026-10-22T14:58+08:00｜**水位**：`v3-0027-lease-request-impl-v4-01`
- **性质**：只读巡检发现，**不代裁、不代写共享状态**；两项均属他席职权，报 Ops 分诊
- **触发**：IMPL-v4-01 收口后待 Integration 租约回执期间，对权威事件流做只读完整性核验

---

## F-1（D1，优先）：权威事件流存在一条畸形 JSONL 记录

- **位置**：`D:\super-develop\runtime\datara-live\events\2026-10-22-restart.jsonl` **第 25 行**
- **事件**：`v3-0025-outbox-reports-admitted-batch-3`（ts 2026-10-22T14:50:00+08:00，actor Flow，type OUTBOX_REPORTS_ADMITTED）
- **症状**：`json.loads` 抛 `Expecting ',' delimiter: line 1 column 1580 (char 1579)`（即行尾截断处）。
- **实测**：该行 `{` 计 **3**、`}` 计 **2** —— **缺一个闭合花括号**；在行尾补一个 `}` 后 `json.loads` **成功**。即根对象末括号缺失（payload 内层 `highlights{}` 与 payload 已闭合，root 未闭合）。
- **排除 transient**：该行之后仍有第 26/27 行（v3-0026/v3-0027），说明该行**已完整写入并换行**，非并发写半截；两次读取（14:56、14:58）结果一致。
- **影响**：依用户裁定 EXC-v4-01 选项 A（v3-0023），本文件已转正为**事件流唯一权威**。任何严格 JSONL 消费方（审计采集器、重放、校验和、外部对账）在该行**硬失败**，且失败点位于流中段 → 其后 v3-0026/v3-0027（含本票 EVIDENCE_READY 与租约请求的登记）在「逐行解析」语义下**不可达**。
- **建议**（他席职权，本席不执行）：
  1. Flow（事件流唯一写手）修复该行末括号，或按既定幂等/追加语义**追加一条补偿记录**并在 payload 注明 `supersedes`/`repair` 指向 v3-0025；**不回写改写历史**与否请 Flow 依事件流纪律裁定。
  2. 修复后重跑校验和与审计采集，确认 v3-0026/v3-0027 恢复可达。
  3. 建议为事件流写手增加**写入后即时 `json.loads` 自检**（fail-closed），防同类截断再现。

## F-2（D1）：治理审计采集器仍读已降级的 mailbox.jsonl（源失准）

- **现象**：`logs/governance-audit-latest.json`（captured_at **14:47:51**）的 `watermark` = `v3-0006-decision-rulings-d01-d04`；而同期活水位已 `v3-0027`。`alerts` 仅 `BLOCKED_WORK×2`，与当前盘面（IMPLEMENTATION blocked 2 仍成立，但 EXCEPTION 已空、REMOTE_TEST 有新项）**不一致**。
- **判因**：采集器源仍为 `docs/handoff/mailbox.jsonl`（按 EXC-v4-01 选项 A 已**降级为非权威快照并冻结于 v3-0006**，Flow 已停止双写）。这与 Ops 既有 **R-2**（审计盲区）同源，且在选项 A 落地后**恶化**为「采集器读冻结源」。
- **建议**（他席职权）：将 `AIDOS-Datara-Governance-Audit`（及 Live-Collector 若同源的）采集源正位至 `events/2026-10-22-restart.jsonl` 与 `governance-state.json` / `queues/snapshot.json`；计划任务生命周期变更仍 USER_ONLY。

## 附：本票进度（供 Ops/Flow 知悉，无请求动作）

- IMPL-v4-01 状态链：`ASSIGNED → EVIDENCE_READY`（**v3-0026**，证据 `outbox/claude/2026-10-22-EXEC-IMPL-v4-01-EVIDENCE-claude.md` + D03 勘误登记 + 租约请求）。
- REMOTE_TEST：`RT-IMPL-V4-01-A-GROUP` **READY**（v3-0027 登记），候 Integration 回执 `LEASE_GRANTED`/`LEASE_DEFERRED`；回执前本席不进 1.9 执行。
- 本席 WIP=1（IMPL-v4-01 未 DONE），不领新票。

## 边界声明

- 本轮仅**只读**核验（`json.loads` 逐行校验 + 采集器产物读取）；**未**修改事件流、**未**修改采集器配置、**未**写 STATE/mailbox/队列投影（Flow 单写）、**未** commit/push、**未**加载 AOCI、**未**弹窗用户。
- 两项发现均属他席职权（Flow 事件流写手 / Ops 采集器与计划任务），本席**不自行修复**，报 Ops 分诊。

—— Execution（claude），事件流完整性巡检发现，报 Ops。

# Ops 巡检报告 · 队列指标 / 采集器 / 审计告警

- 席位: 运行监督 Ops
- 巡检时间: 2026-10-22T13:42:47+08:00
- epoch / lifecycle / 水位: 3 / RUNNING / `v3-0006-decision-rulings-d01-d04`
- 数据来源（全部只读）: queues/snapshot.json、events/2026-10-22-restart.jsonl、logs/governance-audit-latest.json、logs/hard-constraint-audit-latest.json、control/authority-carrier-registry.json、control/remote-test-queue.json、control/policy-receipts.json、docs/handoff/STATE.md、docs/handoff/mailbox.jsonl

## 1. 队列指标

| 队列 | ready | in_progress | blocked | awaiting_downstream |
|---|---|---|---|---|
| DECISION | 0（D01–D04 已裁定 @v3-0006） | 0 | 0 | 0 |
| DISPATCH | 0 | 0 | 0 | 0 |
| IMPLEMENTATION | 6 | 0 | 0 | 0 |
| VALIDATION / INTEGRATION / REMOTE_TEST / EXCEPTION / POLICY_RECEIPT | 1(EXC) / 0 / 0 / 0 / 0 | 0 | 0 | 0 |

- flow_metrics: arrival_rate / service_rate / p90_wait = null，wip = 0（纪元开启后无 ASSIGNED 样本，采集器无数据可算，非故障）。
- **吞吐信号（最重要）**: v3-0005 派单开放（12:29:30）→ v3-0006 裁定（12:45）→ 至巡检时点（13:42）**无任何派单事件**，全实施线闲置约 1 小时。当前最大吞吐杠杆是立即派单。
- **可派单面实际为 4 不是 6**：IMPL-v4-02（待 IMPL-v4-01）与 IMPL-v4-06（待全部 + owner=User 终局）虽计入 ready，但依赖未满足。真实可派：**IMPL-v4-04（派单头，CONTROL/P1，无依赖）→ IMPL-v4-01（P1 关键路径，D03/D04 已解锁）→ IMPL-v4-03（P2，已解锁）→ IMPL-v4-05（P2，无依赖）**。三实施线 WIP=1，可并行消化 4 项中的 3 项。
- ready 计数语义：快照 ready=6 含依赖未满足项，与协作规程"BLOCKED 不占 READY 队首"的口径存在轻微偏差（未占队首，但虚增库存数）。建议 Flow 投影时区分 ready / ready_with_unmet_deps。

## 2. 事件链与共享一致性

- 事件链 v3-0001..v3-0006 完整、时间戳单调、business_key 唯一、epoch=3、幂等键规范 — **PASS**。
- 四载体水位一致：governance-state / snapshot / STATE.md / mailbox.jsonl（repo）均到 v3-0006，且 repo mailbox.jsonl 与 super-develop events 投影逐事件一致。

## 3. 采集器与审计告警

- governance-audit-latest.json（13:32:51 采样，新鲜）: alerts = [] — 采样时点无告警。
- hard-constraint-audit-latest.json: **PASS**，failures = []。
- 计划任务: AIDOS-Datara-Live-Collector / AIDOS-Datara-Governance-Audit 双 ENABLED（v3-0002），13:32 采样证明在跑。
- 1.9 远端: reachable（v3-0002 ping+tcp22），租约 0，REMOTE_TEST 队列空 — 派单前状态正常。
- policy-receipts: POLICY-v3 APPLIED，投影与源事件一致。

## 4. EXCEPTION 队列核查 · EXC-v4-01（重点）

**事实核查结果：异常前提在当前时点不成立（已自愈/已被重建）。**

- EXC-v4-01（12:50 由 Flow 提出）声称：注册表 `mailbox`/`state_view` 两项 ACTIVE 指向 `D:\需求\数据治理工具\Datara\docs\handoff\mailbox.jsonl` 与 `STATE.md`，两文件已被用户移除。
- 实测（13:42）：**两文件均存在**；STATE.md 内容为 RUNNING / v3-0006；mailbox.jsonl 含 v3-0001..v3-0006 全部 6 事件，与 super-develop events 投影逐事件一致。
- 结论：注册表两项 ACTIVE 当前指向有效且新鲜的载体，**注册表现状不再失准**。"采集器/审计持续告警"未出现（alerts=[]），与此相符。

**分类建议**（裁定权与登记权不在 Ops）:
- 建议由 Flow 核实后**降级/关闭** EXC-v4-01：从 P1"载体失准待裁定"降为"已核销"或 D1 级"载体双址正位确认"。
- 若用户仍需对 A/B/C 做正位裁定，影响评估：
  - **A 注册表迁移正位至 super-develop events**：单一正位、消除双写漂移风险、与既有 events 投影现状吻合 — **Ops 推荐**。
  - B 重建 Datara 仓库两载体：即当前已发生的状态，可运行但长期双写有漂移风险，需 Flow 双写纪律兜底。
  - C 标记 REMOVED：注册表失去 mailbox/state_view 的 ACTIVE 锚点，可追溯性最差。
- 紧迫性：低（双址当前同步，无数据丢失风险），不再阻塞任何派单。

## 5. 其他发现（非 EXCEPTION，建议级）

| # | 发现 | 深度 | 责任席 | 建议 |
|---|---|---|---|---|
| R-1 | role-contracts.json 与 remote-test-queue.json 顶层 lifecycle 字段仍为 STOPPED（governance-state/snapshot/协作规程/STATE.md 均为 RUNNING） | D1 | Flow | 下次投影写入时对齐两载体 lifecycle 字段 |
| R-2 | 审计盲区：载体路径失准期间（12:50 起）governance 审计未产生路径存在性告警（若非自愈及时将静默） | D1 | Flow/采集器 | 为 ACTIVE 载体增加路径存在性校验项；计划任务生命周期变更仍 USER_ONLY |
| R-3 | 快照 ready=6 虚增 2（依赖未满足） | D1 | Flow | 投影区分 ready 与 ready_with_unmet_deps |
| R-4 | AGENTS.md 工作区规则仍写"当前为 STOPPED / epoch 3" | D0 | Flow/IMPL-v4-04 | 随 D 组载体入库（IMPL-v4-04 路径含 AGENTS.md）一并修正状态行 |
| R-5 | 派单未落地，WIP=0，三线闲置 | — | Flow/Task | 按派单头执行：IMPL-v4-04 → IMPL-v4-01 →（并行）IMPL-v4-03 / IMPL-v4-05 |

## 6. 边界声明

Ops 本轮仅只读巡检并输出本报告；未写 mailbox/STATE/队列投影，未替 Decision 裁定（A/B/C 仅给建议），未替 Acceptance 验收。EXC-v4-01 的核销/降级登记与 lifecycle 字段对齐由 Flow 执行；正位选项如需裁定走 D4 由用户决定。

# 库存核对与派单调整（增量 11 · v3-0048 外部证据更新）

- **席位**：Task / epoch 3 / RUNNING
- **基线**：`2026-10-22-task-inventory-check-dispatch-10.md` **v1.3**（票面四字段以此为准，本件不重复展开）
- **水位**：v3-0048（18:20:46 后无新事件；IMPL 队列零变化）
- **动作**：吸收 18:31 后 Ops/Integration/Execution 新出件，调整派单线与风险标注；**无新票、无 READY/BLOCKED 状态变更**

## 一、新证据（18:31 后）

| 来源 | 时间 | 对本席的影响 |
|---|---|---|
| Ops 分诊 `ops-triage-exec2-E1E2-P1-C1-v3-0048` | 18:40 | **P-1：明确建议 Flow 尽快扫箱接纳 Task 增量 10 并出 07/08 派单票**；E-1/E-2：EXEC-2 = claude 载体独立线 2（D0 已解释），WIP 按线计；C-1：租约 24h 双源复核成立 |
| Ops 巡检 `ops-inspection-queue-collectors-v3-0048` | 18:28 | READY_STARVATION 结构性见底，无建议派单；trae 静默 2h55m（A1 WATCH）；A3 仍引 20:00 旧口径，已被 C-1 纠正 |
| Integration 巡检 `INT-PATROL-v3-0048` | 18:26 | **LEASE-01 执行段存活不可确证**（`who` 空、无 executor 进程、隔离树 120min 零写入、evidence_dir 未创建）；02a 租约请求仍仅见 outbox，**候 Flow 准入后受理** |
| EXEC-2 心跳 `EXEC-IMPL-v4-02-round2-standby` | 18:38 | EXEC-2 待命、WIP=0、不预领 07/08；E-1 线别仍候 Ops 正式登记 |

## 二、结论与调整

1. **READY 库存不变（2 票）**：`IMPL-v4-07`（P2/DELIVERY，质量批 A）、`IMPL-v4-08`（P2/DELIVERY，API 15-P0 契约冻结）。四字段/依赖/验收/授权/证据见增量 10 v1.3 §四。
2. **派单线细化（致 Flow）**：
   - **07 → EXEC-2（claude 线 2）**：EXEC-1 续持 02a 至回执闭环，EXEC-2 空载可立即开工；两线路径不交叠。
   - **08 → trae**：契约/文档面，与其 03 租约候执不冲突；trae 已静默约 3h，若 Flow 派单后仍无 ACK，建议 **08 回退 EXEC-1**（02a 闭环后）或候用户启用 codex，不在线别未定时预占路径。
3. **关键路径风险升级（Task 侧标注，不越权处置）**：Integration 巡检显示 LEASE-01 **执行段存活不可确证**。若 01 执行段实际未运行，`01 → 02b → 06` 链将继续停摆；请 Ops 向 `claude-lane-loop-executor` 核实心跳/进度，Integration 在租约未到期前不自行释放。Task 待状态变化后再调整 02b/06 排程，不提前改期。
4. **准入仍是唯一吞吐杠杆**：02a EVIDENCE/租约请求与 07~15 票面均未入控制面；Integration 明确不认 outbox 替代队列。**Flow 扫箱 + 出派单票是当前唯一能解除 READY_STARVATION 与 02a 停滞的动作**（Ops P-1 同结论）。
5. **租约口径已收敛**：24h（至 2026-10-23T15:28:04）为控制面真源；增量 10 已升 v1.3，不再按 20:00 设风险。

## 三、未决与触发

- 未决：Flow 准入（02a + 07~15）｜Ops E-1 线别登记｜01 执行段存活核实｜Integration RT-03/RT-02a 回执。
- 触发补位：08 PASS → 09；DEC-D05 → 13；用户 D4 → 14；Decision F-2/F-3 方向 + 01 DONE → 15。
- 本件为增量更新，非重复票面；下轮仅水位/队列/新出件变化时再产出。

---
Task / epoch 3 / 2026-10-22T18:42+08:00 / 水位 v3-0048 / 提交 Flow 接纳

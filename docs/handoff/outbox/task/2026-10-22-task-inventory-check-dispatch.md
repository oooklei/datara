# IMPLEMENTATION 库存核对与派单建议

- **席位**: Task / epoch 3 / RUNNING
- **基线水位**: `v3-0006-decision-rulings-d01-d04`
- **动作性质**: 库存核对 + 派单建议 + 依赖断环建议；提交流程控制 Flow 接纳，Task 不写队列投影

## 一、逐票核对（快照 ready=6）

| 票 | 域/优先级 | 四字段 | 依赖 | 判定 |
|---|---|---|---|---|
| IMPL-v4-01 | DELIVERY P1 | 齐 ✓ | D03/D04 已裁定（v3-0006）✓ | **READY 可派** |
| IMPL-v4-02 | DELIVERY P1 | 齐 ✓ | D01 ✓ + **IMPL-v4-01 未完成 ✗** | **BLOCKED**（不占队首，保位） |
| IMPL-v4-03 | VALIDATION P2 | 齐 ✓ | D02 已裁定 ✓ | **READY 可派** |
| IMPL-v4-04 | CONTROL P1 | 齐 ✓ | 形式无依赖；**实质耦合 EXC-v4-01**（见 §三） | 建议转 **BLOCKED on EXC-v4-01** |
| IMPL-v4-05 | MAINTENANCE P2 | 齐 ✓ | 无 ✓ | **READY 可派** |
| IMPL-v4-06 | CONTROL P1 | 齐 ✓ | 01/02/03/04/05 全未完成 ✗ | **BLOCKED**（终局闸门，owner User） |

**依赖 DAG 无环**：D03/D04→01→02；D01→02；D02→03；(∅)→04,05；{01..05}→06；建议新增 EXC-v4-01→04。确认无循环依赖。

## 二、第一调度周期派单建议（WIP 每线 1，多线并行）

| 序 | 票 | 依据 |
|---|---|---|
| 1 | **IMPL-v4-01** | 唯一 P1 DELIVERY 就绪票；权威设计关键路径（LLM 域），02 的唯一前驱，最早启动最早解锁 |
| 2 | **IMPL-v4-03** | P2 就绪；域序 VALIDATION > MAINTENANCE |
| 3 | **IMPL-v4-05** | P2 就绪，无依赖 |

三线并行无路径冲突（backend/llm+runtime_node、newweb/e2e、仓库根部杂项互不交叠）。

## 三、库存调整建议（需 Flow 接纳）

1. **IMPL-v4-04 转 BLOCKED on EXC-v4-01**：该票为"一次性集成窗提交"，含 `docs/handoff/STATE.md` 与 `docs/handoff/mailbox.jsonl`；EXC-v4-01 的三个候选方案（A 迁移正位 / B 重建 / C 标记 REMOVED）直接决定这两文件的最终处置。先提交则裁定后必返工，且破坏"一次性"语义。整票候裁定，转 BLOCKED 不占队首。
2. **IMPL-v4-01 附加执行注记**（不拆票，随证据包）：DEC-v4-D03 的 §5E.3/WBS15.6 **勘误登记**须随 IMPL-v4-01 证据包一并提交；若节点 A 范围触及 L3-04 后端闸门，按 D01 选项①（后端闸门 + FE 403 错误态）执行。
3. **IMPL-v4-02/03 执行注记**：02 的 FE 侧按 D01 选项①；03 的 tsconfig.node.json include 扩展按 D02（已含于 paths 与验收）。

## 四、库存水位与下游

- 真可派库存：01 / 03 / 05 = **3 票**，加 02（01 完成即转可派）→ 满足"至少一个调度周期"要求。
- 连锁：01 DONE → 02 可派；05+03 DONE 后 04 仍候裁定；全六票 DONE → 06（发布清单交用户，USER_ONLY push）。
- EXC-v4-01（D4）与 IMPL-v4-06（push 授权）均收敛于用户：**可提示用户在同一轮交互中先裁定 EXC-v4-01，再处理发布授权**，避免 04/06 双重等待。
- 远程验证需求：01（1.9 pytest）、02/03（1.9 端到端）均需 Integration 租约；04/05 纯静态审查无远测。

---
Task / epoch 3 / 2026-10-22 / 水位 v3-0006-decision-rulings-d01-d04

# IMPLEMENTATION 库存核对与派单建议（增量 02）

- **席位**: Task / epoch 3 / RUNNING
- **基线水位**: `v3-0006-decision-rulings-d01-d04`（前次：2026-10-22-task-inventory-check-dispatch.md）
- **当前水位**: `v3-0011-scheduler-cadence-ruled-10m`
- **动作性质**: 增量库存核对 + 派单建议；提交流程控制 Flow 接纳，Task 不写队列投影

## 一、变化检测（相对基线）

| 变化项 | 基线 | 当前 | 判定 |
|---|---|---|---|
| 水位 | v3-0006 | **v3-0011-scheduler-cadence-ruled-10m** | 推进（v3-0007..v3-0011） |
| IMPL-v4-04 | READY（建议转 BLOCKED on EXC-v4-01） | **ASSIGNED** → claude，2026-10-22T13:44+08:00，ticket face `fl-dispatch-impl-v4-04-dgroup-v3-0008.json`，event `v3-0008-dispatch-assigned-impl-v4-04` | 状态变更，已派 |
| DECISION | D01-D04 已裁定（v3-0006） | 无新增 | 未变 |
| EXC-v4-01 | D4/P1 候用户裁定 | 同 id / 同 raised_at / 同内容 | 未变 |
| 其余五票（01/02/03/05/06） | 四字段/依赖/验收如基线 | 逐项复核一致 | 未变 |

ready 计数 6→5（04 移出）；快照计数器 blocked=0，但 02/06 实质仍依赖未完成前驱（见 §二）。

## 二、逐票复核（六票）

| 票 | 四字段 | 依赖 | 判定 |
|---|---|---|---|
| IMPL-v4-04 | P1/P1/基线完整性/null ✓ | 形式 ∅；**实质耦合 EXC-v4-01（未裁定）** | ASSIGNED 在飞；残留返工风险见 §四 |
| IMPL-v4-01 | P1/P1/关键路径 LLM 域/null ✓ | D03/D04 已裁定（v3-0006）✓ | **READY，派单队首** |
| IMPL-v4-02 | P1/P1/前端关键路径/null ✓ | D01 ✓ + **IMPL-v4-01 未完成 ✗** | 实质 BLOCKED，不占队首、保位 |
| IMPL-v4-03 | P2/P2/验收链补全/null ✓ | D02 已裁定 ✓ | **READY 可派** |
| IMPL-v4-05 | P2/P2/仓库根部卫生/null ✓ | ∅ ✓ | **READY 可派** |
| IMPL-v4-06 | P1/P1/发布终局闸门/null ✓ | 01..05 全未完成 ✗ | 实质 BLOCKED，owner User |

**依赖 DAG 无环**：D03/D04→01→02；D01→02；D02→03；∅→05；{01..05}→06；04 形式无依赖。无循环。
**BLOCKED 不占队首**：ready 首位为 01，02/06 排后 ✓。
**可派库存 ≥1 调度周期**：01 / 03 / 05 = 3 票 ✓（02 在 01 DONE 后即转可派）。

## 三、下一调度周期派单建议（每线 WIP=1；04 已占一线）

| 序 | 票 | 授权路径 | 证据要求 |
|---|---|---|---|
| 1 | **IMPL-v4-01**（P1 DELIVERY） | Flow 派单票（queue READY + priority_basis：权威设计关键路径 LLM 域，决策卡 A 组） | 1.9 全量 pytest GREEN（Integration 租约）；节点 A/B 证据链闭合；F-1 注释 409/4091→409/4092；**D03 勘误登记随证据包**；如触及 L3-04 按 D01 选项①（后端闸门+FE 403）。链路 EVIDENCE_READY→1.9 ENV_VERIFIED→PASS→集成窗提交 |
| 2 | **IMPL-v4-03**（P2 VALIDATION） | Flow 派单票（D02 已裁定） | 1.9 e2e 可运行并纳入验收链；`npx tsc --noEmit -p tsconfig.node.json` GREEN（含 D02 include 扩展） |
| 3 | **IMPL-v4-05**（P2 MAINTENANCE） | Flow 派单票（无依赖） | 静态审查 + 归档位置登记；**归档优先，删除须用户裁定** |

三线互不交叠：backend llm+runtime_node / newweb e2e / 仓库根部杂项。01 完成后 02 依序补位（FE 侧按 D01 选项①）。

## 四、残留风险与提示

1. **IMPL-v4-04 × EXC-v4-01**：04 已在飞，但 EXC-v4-01 三方案（A 注册表正位 / B 重建载体 / C 标记 REMOVED）直接决定 STATE.md/mailbox.jsonl 终局。若裁定结果与 04 已提交内容冲突，应走 Acceptance REWORK→Flow 重新接纳，不另行派票。
2. **收敛于用户的两项**：EXC-v4-01（D4 裁定）与 IMPL-v4-06（push 授权）均 USER_ONLY，建议用户同一轮交互先裁定 EXC-v4-01、再处理发布授权。
3. 无新增 DECISION/EXCEPTION；无依赖满足状态翻转。

---
Task / epoch 3 / 2026-10-22 / 水位 v3-0011-scheduler-cadence-ruled-10m / 提交 Flow 接纳

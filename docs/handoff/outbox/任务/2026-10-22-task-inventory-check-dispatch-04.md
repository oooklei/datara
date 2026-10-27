# IMPLEMENTATION 库存核对与派单建议（增量 04）

- **席位**: Task / epoch 3 / RUNNING
- **基线水位**: `v3-0017-dispatch-assigned-impl-v4-03`（前次：2026-10-22-task-inventory-check-dispatch-03.md）
- **当前水位**: `v3-0018-integration-commit-impl-v4-04`
- **动作性质**: 增量库存核对 + 派单建议；提交流程控制 Flow 接纳，Task 不写队列投影

## 一、变化检测（相对基线）

| 变化项 | 基线（增量 03） | 当前 | 判定 |
|---|---|---|---|
| 水位 | v3-0017 | **v3-0018-integration-commit-impl-v4-04** | 推进 |
| IMPL-v4-04 | PASS（待集成窗提交） | **DONE**，event `v3-0018`，commit `ef18c2d` | 状态变更：集成窗提交落地，完成链闭合（EVIDENCE_READY → ENV_VERIFIED → PASS → RELEASED/DONE） |
| IMPL-v4-05 | READY（增量 03 建议派单序 1） | **仍 READY，未被派单** | 前次派单建议未被 Flow 采纳，本轮重申 |
| IMPL-v4-01 | ASSIGNED（claude） | ASSIGNED（claude，2026-10-22T14:20+08:00） | 未变，在飞 |
| IMPL-v4-03 | ASSIGNED（trae） | ASSIGNED（trae，2026-10-22T14:20+08:00） | 未变，在飞 |
| DECISION | D01-D04 已裁定（v3-0006） | 无新增 | 未变 |
| EXC-v4-01 | D4/P1 候用户裁定（A/B/C 三方案） | 同 id / 同 raised_at / 同内容 | 未变 |
| 队列计数 | ready 1 / assigned 2 / blocked 2 | ready 1 / assigned 2 / blocked 2 | 计数未变；04 由在飞位转 DONE 位，05 仍占 READY 位 |

## 二、逐票复核（六票）

| 票 | 四字段（base/effective/basis/override） | 依赖 | 判定 |
|---|---|---|---|
| IMPL-v4-01 | P1/P1/权威设计关键路径 LLM 域；停机在飞残留首位（决策卡 A 组）/null ✓ | D03、D04 已裁定（v3-0006）✓ | **ASSIGNED 在飞**（claude） |
| IMPL-v4-02 | P1/P1/前端关键路径；PROJ-FE-01 候裁解锁（决策卡 B 组）/null ✓ | D01 ✓（选项①）+ IMPL-v4-01 未完成 ✗ | 实质 BLOCKED，不占队首、保位；01 DONE 后即转可派 |
| IMPL-v4-03 | P2/P2/验收链补全（决策卡 C 组）/null ✓ | D02 已裁定 ✓ | **ASSIGNED 在飞**（trae） |
| IMPL-v4-04 | P1/P1/epoch 3 运行期载体须入库（决策卡 D 组）/null ✓ | 形式 ∅ ✓ | **DONE**（ef18c2d）；验收标准（Flow 一致性核对 + 静态审查 PASS）已满足。残留耦合：EXC-v4-01 若裁定与已提交载体冲突，走 Acceptance REWORK → Flow 重新接纳，不另派票 |
| IMPL-v4-05 | P2/P2/仓库根部卫生（决策卡 E 组）/null ✓ | ∅ ✓ | **READY，唯一可派**（本周期仍未派单） |
| IMPL-v4-06 | P1/P1/发布终局闸门（USER_ONLY，HC-09）/null ✓ | 01..05：04 DONE，01/03 在飞，02 BLOCKED，05 READY | 实质 BLOCKED，owner User，不占队首 |

**依赖 DAG 无环**：D03/D04→01→02；D01→02；D02→03；∅→05；∅→04（DONE）；{01..05}→06。无循环。
**BLOCKED 不占 READY 队首**：READY 队首仅 05；02/06 排后 ✓。
**可派库存 ≥1 调度周期**：READY = {05} 恰为 1，连续第二周期触底；05 派出后 READY 归零，回填唯一来源为 01 完成解锁 02。

## 三、下一调度周期派单建议（每线 WIP=1）

| 序 | 票 | 授权路径 | 证据要求 |
|---|---|---|---|
| 1 | **IMPL-v4-05**（P2 MAINTENANCE，重申增量 03 建议） | Flow 派单票（无依赖 + queue READY + priority_basis：仓库根部卫生，决策卡 E 组）；当前载体占用：claude→01、trae→03，**codex 为唯一 WIP=0 载体**，建议派至 codex（载体分配权在 Flow） | 静态审查 + 归档位置登记；**归档优先，删除须用户裁定**；路径以票面 paths 六项为准（anchor_cycle.ps1 / append_s375.ps1 / check_outbox.ps1 / check_outbox_result.txt / state_s310.ps1 / workflows/） |

- **01 / 03 继续在飞，不重复派单**（防重复产出）。
- 路径无碰撞：05（仓库根部杂项）与 01（datara-backend/rebuild/**、llmApi.ts）及 03（e2e/、playwright.config.ts、tsconfig.node.json、datara-l12-e2e/）互不交叠。
- **序位预约**：01 完成（PASS）后 02 立即依序补位派单（FE 侧按 D01 选项①：后端闸门 + FE 403 错误态），证据要求：契约测试 + 1.9 端到端 GREEN。

## 四、风险与提示

1. **库存持续触底**：05 已连续两个周期待派。若 Flow 本周期仍不派 05，READY 将继续停留 1 但实质停滞；建议 Flow 优先处理本建议。05 派出后 READY 归零，属六票计划边界内的结构性触底，非 Task 可再造库存（剩余范围受计划封闭约束），回填完全依赖 01 完成速度。
2. **收敛于用户的两项不变**：EXC-v4-01（D4 裁定，A 注册表正位 / B 重建载体 / C 标记 REMOVED）与 IMPL-v4-06（push 授权）均 USER_ONLY；建议用户同一轮交互先裁 EXC-v4-01、再处理发布授权。采集器/审计告警将持续至裁定落地。
3. **IMPL-v4-04 已闭环**：ef18c2d 入库后无待办；仅保留 EXC-v4-01 裁定冲突时的 REWORK 通道。
4. 无新增 DECISION/EXCEPTION；无依赖满足状态翻转（04 DONE 为完成链自然推进，其依赖本就为空）。

---
Task / epoch 3 / 2026-10-22 / 水位 v3-0018-integration-commit-impl-v4-04 / 提交 Flow 接纳

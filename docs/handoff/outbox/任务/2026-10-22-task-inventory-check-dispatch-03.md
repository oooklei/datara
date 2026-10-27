# IMPLEMENTATION 库存核对与派单建议（增量 03）

- **席位**: Task / epoch 3 / RUNNING
- **基线水位**: `v3-0011-scheduler-cadence-ruled-10m`（前次：2026-10-22-task-inventory-check-dispatch-02.md）
- **当前水位**: `v3-0017-dispatch-assigned-impl-v4-03`
- **动作性质**: 增量库存核对 + 派单建议；提交流程控制 Flow 接纳，Task 不写队列投影

## 一、变化检测（相对基线）

| 变化项 | 基线（增量 02） | 当前 | 判定 |
|---|---|---|---|
| 水位 | v3-0011 | **v3-0017-dispatch-assigned-impl-v4-03** | 推进（v3-0012..v3-0017；v3-0012..0014 未在快照条目显式呈现，不作推断） |
| IMPL-v4-04 | ASSIGNED（在飞） | **PASS**，event `v3-0015-acceptance-pass-impl-v4-04` | 状态变更：验收通过，待集成窗提交（RELEASED） |
| IMPL-v4-01 | READY（建议派单序 1） | **ASSIGNED** → claude，2026-10-22T14:20+08:00，ticket face `fl-dispatch-impl-v4-01.json`，event `v3-0016` | 状态变更：建议序 1 已被采纳派单 |
| IMPL-v4-03 | READY（建议派单序 2） | **ASSIGNED** → trae，2026-10-22T14:20+08:00，ticket face `fl-dispatch-impl-v4-03.json`，event `v3-0017` | 状态变更：建议序 2 已被采纳派单 |
| DECISION | D01-D04 已裁定（v3-0006） | 无新增 | 未变 |
| EXC-v4-01 | D4/P1 候用户裁定（A/B/C 三方案） | 同 id / 同 raised_at / 同内容 | 未变 |
| 队列计数 | ready 5 / assigned 1 / blocked 0 | ready 1 / assigned 2 / blocked 2 | 计数器与实质状态对齐 |

## 二、逐票复核（六票）

| 票 | 四字段 | 依赖 | 判定 |
|---|---|---|---|
| IMPL-v4-01 | P1/P1/权威设计关键路径 LLM 域；停机在飞残留首位（决策卡 A 组）/null ✓ | D03、D04 已裁定（v3-0006）✓ | **ASSIGNED 在飞**（claude） |
| IMPL-v4-02 | P1/P1/前端关键路径；PROJ-FE-01 候裁解锁（决策卡 B 组）/null ✓ | D01 ✓（选项①）+ IMPL-v4-01 未完成 ✗ | 实质 BLOCKED，不占队首、保位；01 DONE 后即转可派 |
| IMPL-v4-03 | P2/P2/验收链补全（决策卡 C 组）/null ✓ | D02 已裁定 ✓ | **ASSIGNED 在飞**（trae） |
| IMPL-v4-04 | P1/P1/epoch 3 运行期载体须入库（决策卡 D 组）/null ✓ | 形式 ∅ | **PASS**（纯载体无远测需求）；残留 EXC-v4-01 耦合风险同增量 02 §四.1，若裁定冲突走 REWORK |
| IMPL-v4-05 | P2/P2/仓库根部卫生（决策卡 E 组）/null ✓ | ∅ ✓ | **READY，唯一可派** |
| IMPL-v4-06 | P1/P1/发布终局闸门（USER_ONLY，HC-09）/null ✓ | 01..05：04 已 PASS，01/03 在飞，02 BLOCKED，05 READY | 实质 BLOCKED，owner User |

**依赖 DAG 无环**：D03/D04→01→02；D01→02；D02→03；∅→05；{01..05}→06。无循环。
**BLOCKED 不占队首**：READY 队首仅 05；02/06 排后 ✓。
**可派库存 ≥1 调度周期**：现 READY = {05} 恰为 1，满足下限但已触底；01 DONE 后 02 补位回填。

## 三、下一调度周期派单建议（每线 WIP=1）

| 序 | 票 | 授权路径 | 证据要求 |
|---|---|---|---|
| 1 | **IMPL-v4-05**（P2 MAINTENANCE） | Flow 派单票（无依赖 + queue READY + priority_basis：仓库根部卫生，决策卡 E 组）；建议派至 04 PASS 后释放的实施线 | 静态审查 + 归档位置登记；**归档优先，删除须用户裁定**；路径以票面 paths 六项为准（anchor_cycle.ps1 / append_s375.ps1 / check_outbox.ps1 / check_outbox_result.txt / state_s310.ps1 / workflows/） |

- **01 / 03 继续在飞，不重复派单**（防重复产出）。
- 路径无碰撞：05（仓库根部杂项）与 01（datara-backend/rebuild/**、llmApi.ts）及 03（e2e/、playwright.config.ts、tsconfig.node.json、datara-l12-e2e/）互不交叠。
- **序位预约**：01 完成（PASS）后 02 立即依序补位派单（FE 侧按 D01 选项①：后端闸门 + FE 403 错误态），证据要求沿用增量 02 建议序内条款（契约测试 + 1.9 端到端 GREEN）。

## 四、风险与提示

1. **库存触底预警**：05 本周期派出后 READY 归零，回填依赖 01 完成解锁 02。Task 将随水位推进持续巡检；若 01/03 出现 REWORK 或异常，及时重排。
2. **收敛于用户的两项不变**：EXC-v4-01（D4 裁定，A 注册表正位 / B 重建载体 / C 标记 REMOVED）与 IMPL-v4-06（push 授权）均 USER_ONLY；建议用户同一轮交互先裁 EXC-v4-01、再处理发布授权。采集器/审计告警将持续至裁定落地。
3. **IMPL-v4-04 后续**：PASS 后待 Flow/Integration 完成集成窗提交（RELEASED）；如 EXC-v4-01 裁定结果与 04 已提交载体冲突，走 Acceptance REWORK→Flow 重新接纳，不另派票。
4. 无新增 DECISION/EXCEPTION；无依赖满足状态翻转（01→ASSIGNED 为派单动作，其依赖 D03/D04 早已满足）。

---
Task / epoch 3 / 2026-10-22 / 水位 v3-0017-dispatch-assigned-impl-v4-03 / 提交 Flow 接纳

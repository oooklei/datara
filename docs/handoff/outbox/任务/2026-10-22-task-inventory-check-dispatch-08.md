# IMPLEMENTATION 库存核对与派单建议（增量 08）

- **席位**: Task / epoch 3 / RUNNING
- **基线水位**: `v3-0038-acceptance-verdicts-user-directive-02a-admitted-batch-5`（前次：2026-10-22-task-inventory-check-dispatch-07.md）
- **当前水位**: `v3-0042-exc-v4-03-concurrent-flow-writers`
- **动作性质**: 增量库存核对 + 派单建议（本周期无新派单，登记回填触发器与例外核实项）；提交流程控制 Flow 接纳，Task 不写队列投影

## 一、变化检测（相对基线）

| 变化项 | 基线（增量 07） | 当前（快照 v3-0042） | 判定 |
|---|---|---|---|
| 水位 | v3-0038 | **v3-0042-exc-v4-03-concurrent-flow-writers**（途经 v3-0039 / v3-0041 / v3-0042） | 推进 |
| IMPL-v4-05 | PASS（候集成窗提交） | **DONE**（v3-0039 集成窗提交，commit 835939c，main，11 files +328，NO_SECRET 0 命中） | 状态变更 |
| IMPL-v4-02 | BLOCKED（整票） | **父票移除，拆分落定**：02a **ASSIGNED**（v3-0041，指名 claude，承接增量 07 第三节零修订）；02b 独立 BLOCKED 票面（候 01 契约冻结） | 票目结构变更（02a 新增 ASSIGNED、02b 新增 BLOCKED） |
| IMPL-v4-01 | REWORK（候租约回执） | REWORK，租约 RT-IMPL-V4-01-A-GROUP 仍 READY 候回执 | 未变 |
| IMPL-v4-03 | REWORK（候 1.9 e2e 实跑） | REWORK，仍无 REMOTE_TEST 租约请求 | 未变 |
| IMPL-v4-04 | DONE（ef18c2d） | DONE | 未变 |
| IMPL-v4-06 | BLOCKED | BLOCKED，blocked_reason 更新（02 拆分后依赖解释为 {01,02a,02b,03,04,05}；push 预授权 v3-0023 不变） | 票面附注变更 |
| REMOTE_TEST | RT-IMPL-V4-01-A-GROUP READY | 仍 READY，租约回执未出 | 未变 |
| DECISION | D01-D04 已裁定（v3-0006） | 无新增 | 未变 |
| EXCEPTION | EXC-v4-01/02 均核销 | 水位名含 **EXC-v4-03（concurrent flow writers，v3-0042）**，但快照 EXCEPTION 段仅有 ruled EXC-v4-01 / ruled_2 EXC-v4-02，**无 EXC-v4-03 明细或裁定条目** | 例外变动（登记状态待核实） |
| 队列计数 | ready 0 / in_progress 2 / blocked 2 / awaiting_downstream 1（wip 3） | ready 0 / assigned 1 / in_progress 2 / blocked 2（wip 2） | 计数变化（02a 落 ASSIGN、05 DONE） |

**触发判定**：水位推进 + 票目新增/状态变更（05 DONE、02a ASSIGNED、02b 新票、06 附注更新）+ EXCEPTION 变动（EXC-v4-03）→ 产出本增量。

## 二、逐票复核（七票）

| 票 | 四字段（base/effective/basis/override） | 依赖 | 验收 | 判定 |
|---|---|---|---|---|
| IMPL-v4-01 | P1/P1/权威设计关键路径 LLM 域；停机在飞残留首位（决策卡 A 组）/null | D03、D04 ✓（v3-0006） | 1.9 全量 pytest GREEN + 节点 A/B 证据链闭合 + F-1 注释修正（409/4091→409/4092） | REWORK（v3-0033）；候租约回执，回执前不进 1.9 执行 |
| IMPL-v4-02a | P1/P1/前端关键路径 02a 段；v3-0031 用户授权部分解耦先行段/null | ∅（边界闸门 v3-0035 已满足） | sshNode 域契约测试 + 本机静态校验 + 1.9 端到端 GREEN（sshNode 域） | ASSIGNED（v3-0041，claude）；与增量 07 第三节票面零偏差 ✓ |
| IMPL-v4-02b | P1/P1/前端关键路径 02b 段；D01 选项① 落地段（后端闸门 + FE 403 错误态）/null | D01 ✓（v3-0006）+ IMPL-v4-01 ✗（契约冻结） | 契约测试 + 1.9 端到端 GREEN（datasource/rolePermissions/PermissionMatrix 域） | BLOCKED 保位；01 DONE 后补位派单 |
| IMPL-v4-03 | P2/P2/验收链补全（决策卡 C 组）/null | D02 ✓（v3-0006） | 1.9 e2e 可运行并纳入验收链 + npx tsc --noEmit -p tsconfig.node.json 通过 | REWORK（v3-0034）；需先出租约请求，Integration 排程 |
| IMPL-v4-04 | P1/P1/基线完整性：epoch 3 运行期载体须入库（决策卡 D 组）/null | ∅ | Flow 一致性核对 + 静态审查 PASS | DONE（ef18c2d）闭环 |
| IMPL-v4-05 | P2/P2/仓库根部卫生（决策卡 E 组）/null | ∅ | 仓库根部无散落杂项 + 归档位置登记 | DONE（835939c，v3-0039）闭环；物理删除候用户裁定，不入票 |
| IMPL-v4-06 | P1/P1/发布终局闸门（USER_ONLY，HC-09）/null | {01,02a,02b,03,04,05}：04✓ 05✓，01/02a/02b/03 ✗ | 发布清单就绪 + 用户授权 push | BLOCKED 保位，owner User |

**依赖 DAG 无环**：D03/D04→01→02b；D01→02b；D02→03；∅→02a；∅→04/05（DONE）；{01,02a,02b,03,04,05}→06。无循环 ✓。
**BLOCKED 不占 READY 队首**：IMPLEMENTATION ready=0；02b/06 排后 ✓。
**可派库存**：IMPLEMENTATION READY=0（结构性触底）。存量票中 02b 候 01 契约冻结、06 候全终态，均不满足派单前置；WBS v4 范围内不存在可合规铸造的新 READY 票（破依赖即违规）。最近回填触发器 = **RT-IMPL-V4-01-A-GROUP 租约回执 → 01 1.9 实跑 → 契约冻结 → 02b 补位**。完成链在飞 3 票（01/02a/03），吞吐瓶颈仍在 1.9 租约与实跑环节。

## 三、派单建议（本周期）

**无新派单**。理由：READY=0 为结构性触底，所有存量票前置未满足；依规程不越权铸造无权威设计依据的新票、不提前解锁 02b。

**回填触发器登记**（提交 Flow/Ops 作为调度观察点）：

| 序 | 触发器 | 后续动作 | 授权路径 | 证据/回执要求 |
|---|---|---|---|---|
| 1 | RT-IMPL-V4-01-A-GROUP 租约回执（Integration 出具） | claude 1.9 隔离执行全量 pytest → 证据回执 → Acceptance 复验升级 PASS | Integration 依 v3-0027 租约请求回执（LEASE_GRANTED/LEASE_DEFERRED） | 1.9 全量 pytest GREEN + 节点 A/B 证据链闭合复核 + MySQL 专有路径结果 |
| 2 | IMPL-v4-01 复验 PASS + 契约冻结 | 02b 补位派单（票面已备，零修订即派） | Flow 依 02b 票面出派单票 | 契约测试 + 1.9 端到端 GREEN（datasource/rolePermissions/PermissionMatrix 域） |
| 3 | IMPL-v4-02a EVIDENCE_READY | 走完成链 ENV_VERIFIED → PASS → 集成窗提交 | Integration 租约核验 → Acceptance 审查 | sshNode 域契约测试记录 + 静态校验输出 + 1.9 e2e 证据 |
| 4 | IMPL-v4-03 出具租约请求 | Integration 按证据件 §5 排程 1.9 e2e 实跑 | 03 线先出租约请求（当前缺失，建议尽快补出） | 1.9 实跑 GREEN → 复验升级 PASS → 集成窗提交 |
| 5 | {01,02a,02b,03,04,05} 全终态 | 06 发布清单聚合，交用户一次性授权 push | USER_ONLY（HC-09；push 预授权在案 v3-0023，执行仍以用户授权记录为凭） | 发布清单 + 用户授权记录 + push 结果 |

## 四、例外与风险提示

1. **EXC-v4-03 核实（本增量唯一未闭环观察项）**：水位名 `v3-0042-exc-v4-03-concurrent-flow-writers` 表明该例外已登记（concurrent flow writers，疑似并发写手冲突），但队列快照 EXCEPTION 段无其明细/裁定条目。按路由（例外分类归 Ops、登记归 Flow）提请 Ops 核实登记与核销状态；Task 不越权裁定，仅记录观察。若涉及队列投影一致性，建议 Flow 在下轮快照中补全或标注。
2. **claude 线 WIP 记账**：01（REWORK，租约候执段）与 02a（ASSIGNED，本地段）并行关系由 Flow 依委派约束核定；Task 依 v3-0035 指令建议，不代记账。
3. **02a 与 03 路径边界**：02a paths 不含 datara-newweb/e2e/；若实施期需新增 sshNode e2e 用例，经 Ops 路由避免与 03（e2e/ 属主）碰撞，不静默扩边。
4. **06 勿提前制备**：发布清单候六票全终态后聚合；02 拆分不改变 06 的 USER_ONLY 终局性质。
5. **可派库存触底属结构性**：非调度缺陷；瓶颈解除动作集中在租约回执（触发器 1）与 03 租约请求补出（触发器 4）。

---
Task / epoch 3 / 2026-10-22 / 基线 v3-0038 → 当前 v3-0042-exc-v4-03-concurrent-flow-writers / 提交 Flow 接纳

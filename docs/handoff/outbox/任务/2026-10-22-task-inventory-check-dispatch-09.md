# IMPLEMENTATION 库存核对与派单建议（增量 09）

- **席位**: Task / epoch 3 / RUNNING
- **基线水位**: `v3-0042-exc-v4-03-concurrent-flow-writers`（前次：2026-10-22-task-inventory-check-dispatch-08.md）
- **当前水位**: `v3-0045-lease-request-rt-impl-v4-03-c-group`
- **动作性质**: 增量库存核对 + 派单建议（本周期无新派单，登记触发器 1/4 已满足与串行排程观察项）；提交流程控制 Flow 接纳，Task 不写队列投影

## 一、变化检测（相对基线）

| 变化项 | 基线（增量 08） | 当前（快照 v3-0045） | 判定 |
|---|---|---|---|
| 水位 | v3-0042 | **v3-0045**（途经 v3-0043 / v3-0044 / v3-0045；v3-0044=租约授予、v3-0045=03 租约请求入队；v3-0043 明细未在快照中展开，不影响本核对结论） | 推进 |
| RT-IMPL-V4-01-A-GROUP | READY（候租约回执） | **LEASED**（v3-0044 LEASE_GRANTED：granted 15:28:04，lease_until 20:00:00，executor claude-lane-loop-executor；governance-state active_leases 已登记 ACTIVE） | 状态变更（触发器 1 满足） |
| RT-IMPL-V4-03-C-GROUP | 不存在（03 租约请求缺失，增量 08 触发器 4 催办中） | **新增 READY**（v3-0045 租约请求已入队，单环境串行自动排于 LEASE-IMPL-V4-01-A-GROUP 之后） | 票目新增（触发器 4 满足） |
| IMPL-v4-01 | REWORK，候租约回执 | REWORK，租约已生效，1.9 隔离执行段进行中 | 状态推进（票面状态字不变） |
| IMPL-v4-03 | REWORK，无租约请求 | REWORK，租约请求已出，候 Integration 排程 | 状态推进（票面状态字不变） |
| IMPL-v4-02a | ASSIGNED（v3-0041） | ASSIGNED，无变化 | 未变 |
| IMPL-v4-02b / 04 / 05 / 06 | 02b BLOCKED、04 DONE(ef18c2d)、05 DONE(835939c)、06 BLOCKED | 均无变化 | 未变 |
| DECISION | D01-D04 已裁定（v3-0006） | 无新增 | 未变 |
| EXCEPTION | EXC-v4-01/02 均核销；EXC-v4-03 登记待核实 | EXCEPTION 段仍仅 ruled EXC-v4-01 / ruled_2 EXC-v4-02，**EXC-v4-03 仍无明细/裁定条目** | 未变（观察项延续） |
| 队列计数 | IMPLEMENTATION：ready 0 / assigned 1 / in_progress 2 / blocked 2（wip 2） | 同值 | 未变 |
| REMOTE_TEST 计数 | ready 1（01-A-GROUP）/ in_progress 0 | ready 1（03-C-GROUP）/ **in_progress 1（01-A-GROUP LEASED）** | 计数变化 |

**触发判定**：水位推进 + REMOTE_TEST 票目状态变更（01-A-GROUP LEASED）+ 新增票目（03-C-GROUP READY）→ 产出本增量。

## 二、逐票复核（七票）

| 票 | 四字段（base/effective/basis/override） | 依赖 | 验收 | 判定 |
|---|---|---|---|---|
| IMPL-v4-01 | P1/P1/权威设计关键路径 LLM 域；停机在飞残留首位（决策卡 A 组）/null | D03、D04 ✓（v3-0006） | 1.9 全量 pytest GREEN + 节点 A/B 证据链闭合 + F-1 注释修正（409/4091→409/4092） | REWORK（v3-0033）；租约已生效（v3-0044，至 20:00），1.9 执行中，候证据回执 |
| IMPL-v4-02a | P1/P1/前端关键路径 02a 段；v3-0031 用户授权部分解耦先行段/null | ∅（边界闸门 v3-0035 已满足） | sshNode 域契约测试 + 本机静态校验 + 1.9 端到端 GREEN（sshNode 域） | ASSIGNED（v3-0041，claude）本地段执行中；与 01 租约候执段不冲突 ✓ |
| IMPL-v4-02b | P1/P1/前端关键路径 02b 段；D01 选项① 落地段（后端闸门 + FE 403 错误态）/null | D01 ✓（v3-0006）+ IMPL-v4-01 ✗（契约冻结） | 契约测试 + 1.9 端到端 GREEN（datasource/rolePermissions/PermissionMatrix 域） | BLOCKED 保位；01 契约冻结后补位派单（票面已备） |
| IMPL-v4-03 | P2/P2/验收链补全（决策卡 C 组）/null | D02 ✓（v3-0006） | 1.9 e2e 可运行并纳入验收链 + npx tsc --noEmit -p tsconfig.node.json 通过 | REWORK（v3-0034）；租约请求已出（v3-0045），候 Integration 排程（串行于 lease-01 后） |
| IMPL-v4-04 | P1/P1/基线完整性：epoch 3 运行期载体须入库（决策卡 D 组）/null | ∅ | Flow 一致性核对 + 静态审查 PASS | DONE（ef18c2d）闭环 |
| IMPL-v4-05 | P2/P2/仓库根部卫生（决策卡 E 组）/null | ∅ | 仓库根部无散落杂项 + 归档位置登记 | DONE（835939c，v3-0039）闭环；物理删除候用户裁定 |
| IMPL-v4-06 | P1/P1/发布终局闸门（USER_ONLY，HC-09）/null | {01,02a,02b,03,04,05}：04✓ 05✓，01/02a/02b/03 ✗ | 发布清单就绪 + 用户授权 push | BLOCKED 保位，owner User，勿提前制备 |

**依赖 DAG 无环**：D03/D04→01→02b；D01→02b；D02→03；∅→02a；∅→04/05（DONE）；{01,02a,02b,03,04,05}→06。无循环 ✓。
**BLOCKED 不占 READY 队首**：IMPLEMENTATION ready=0；02b/06 排后 ✓。
**可派库存**：IMPLEMENTATION READY=0（结构性触底延续，与增量 08 结论一致）。02b 候 01 契约冻结、06 候六票全终态，前置均未满足；WBS v4 范围内无可合规铸造的新 READY 票。完成链在飞 3 票（01 租约执行中 / 02a 本地执行中 / 03 租约候排程）；瓶颈已从「租约请求缺失」收敛为「1.9 单环境串行实跑吞吐」。

## 三、派单建议（本周期）

**无新派单**。理由：READY=0 结构性触底延续，存量票前置均未满足；依规程不越权铸造无权威设计依据的新票、不提前解锁 02b、不替 06 提前制备发布清单。

**触发器状态更新**（承接增量 08 登记）：

| 序 | 触发器 | 状态 | 后续动作 | 授权路径 | 证据/回执要求 |
|---|---|---|---|---|---|
| 1 | RT-IMPL-V4-01-A-GROUP 租约回执 | **已满足**（v3-0044 LEASE_GRANTED，租约至 20:00） | claude 1.9 隔离执行全量 pytest → 证据回执 → Acceptance 复验升级 PASS | Integration 租约回执在案 | 1.9 全量 pytest GREEN + 节点 A/B 证据链闭合复核 + MySQL 专有路径结果 |
| 2 | IMPL-v4-01 复验 PASS + 契约冻结 | 待（依赖触发器 1 产物） | 02b 补位派单（零修订即派） | Flow 依 02b 票面出派单票 | 契约测试 + 1.9 端到端 GREEN（datasource/rolePermissions/PermissionMatrix 域） |
| 3 | IMPL-v4-02a EVIDENCE_READY | 待 | 走完成链 ENV_VERIFIED → PASS → 集成窗提交 | Integration 租约核验 → Acceptance 审查 | sshNode 域契约测试记录 + 静态校验输出 + 1.9 e2e 证据 |
| 4 | IMPL-v4-03 出具租约请求 | **已满足**（v3-0045 已入队 READY） | Integration 按证据件 §5 排程 1.9 e2e 实跑（串行于 lease-01 后） | Integration 排程裁定 | 1.9 实跑 GREEN（7 tests，E2E_PASS 运行时注入）→ 复验升级 PASS → 集成窗提交；datara-l12-e2e 1.9 侧安排候回执裁定 |
| 5 | {01,02a,02b,03,04,05} 全终态 | 待 | 06 发布清单聚合，交用户一次性授权 push | USER_ONLY（HC-09；push 预授权在案 v3-0023） | 发布清单 + 用户授权记录 + push 结果 |

## 四、例外与风险提示

1. **EXC-v4-03 核实项延续（未闭环，非本周期新增）**：快照 EXCEPTION 段仍无 EXC-v4-03 明细/裁定条目。维持增量 08 建议：提请 Ops 核实登记与核销状态，Flow 下轮快照补全或标注。Task 不越权裁定。
2. **1.9 单环境串行排程风险**：lease-01 至 20:00；若实跑超时或租约到期未完成，RT-IMPL-V4-03-C-GROUP 串行顺延，02b 补位与 06 聚合链路同步后移。建议 Ops 关注租约到期与 lease 续期/回收裁定（Integration 职权）。
3. **v3-0043 事件明细未展开**：水位途经事件 v3-0043 在快照中无条目级信息；本核对以 v3-0044/v3-0045 可见事件为锚，结论不受影响；如需溯源由 Flow 依 mailbox 提供，Task 不另行注入全量事件流。
4. **claude 线 WIP 记账**：01（REWORK，1.9 租约执行段）与 02a（ASSIGNED，本地段）并行关系维持增量 08 口径，由 Flow 依委派约束核定，Task 不代记账。
5. **02a 与 03 路径边界**：02a paths 不含 datara-newweb/e2e/；若实施期需新增 sshNode e2e 用例，经 Ops 路由避免与 03（e2e/ 属主）碰撞。

---
Task / epoch 3 / 2026-10-22 / 基线 v3-0042 → 当前 v3-0045-lease-request-rt-impl-v4-03-c-group / 提交 Flow 接纳

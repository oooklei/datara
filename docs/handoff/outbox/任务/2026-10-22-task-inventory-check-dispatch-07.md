# IMPLEMENTATION 库存核对与派单建议（增量 07）

- **席位**: Task / epoch 3 / RUNNING
- **基线水位**: `v3-0031-outbox-reports-admitted-batch-4`（前次：2026-10-22-task-inventory-check-dispatch-06.md）
- **当前水位**: `v3-0038-acceptance-verdicts-user-directive-02a-admitted-batch-5`
- **动作性质**: 增量库存核对 + IMPL-v4-02a 派单确认建议（依 v3-0035 用户指令）；提交流程控制 Flow 接纳，Task 不写队列投影

## 一、变化检测（相对基线）

| 变化项 | 基线（增量 06） | 当前 | 判定 |
|---|---|---|---|
| 水位 | v3-0031 | **v3-0038-acceptance-verdicts-user-directive-02a-admitted-batch-5** | 推进（验收裁定批次 + 用户指令 02a 批次 5 接纳） |
| IMPL-v4-01 | EVIDENCE_READY | **REWORK**（v3-0033：Acceptance 复核——代码面零返工，F-1/节点 A 结论维持有效；缺口仅 1.9 全量 pytest GREEN + 节点 B 证据链含 MySQL 专有路径；租约 RT-IMPL-V4-01-A-GROUP 候回执，回执后 1.9 隔离执行 → 证据回执 → 复验升级 PASS） | 状态变更 |
| IMPL-v4-03 | EVIDENCE_READY | **REWORK**（v3-0034：代码面零返工；缺口仅 1.9 e2e 实跑证据；03 尚无 REMOTE_TEST 租约请求，Integration 按证据件 §5 排程） | 状态变更 |
| IMPL-v4-05 | EVIDENCE_READY | **PASS**（v3-0032：独立复核全过——根部 10 件残留 NONE、保护资产原位、归档区 10 件+MANIFEST 逐件登记、零删除，物理删除候用户裁定）→ 候 Flow 集成窗提交 | 状态变更 |
| IMPL-v4-02 | BLOCKED（v3-0031 部分解耦附注） | BLOCKED，blocked_reason **增补 v3-0035 用户指令（Ops 转达）**：02a 指名派单 claude，Task 票面落地后即派（claude 线自 v3-0026 起空闲） | 票面附注变更（指向 Task 派单确认） |
| IMPL-v4-04 | DONE（ef18c2d） | DONE | 未变 |
| IMPL-v4-06 | BLOCKED（push 预授权在案 v3-0023） | BLOCKED | 未变 |
| REMOTE_TEST | RT-IMPL-V4-01-A-GROUP READY | 仍 READY，租约回执未出 | 未变 |
| DECISION | D01-D04 已裁定（v3-0006） | 无新增 | 未变 |
| EXCEPTION | EXC-v4-01/02 均核销 | 无新增 | 未变 |
| 队列计数 | ready 0 / in_progress 3 / blocked 2 | ready 0 / in_progress 2 / blocked 2 / awaiting_downstream 1（wip 3） | 计数变化（随三票状态迁移） |

**触发判定**：水位推进 + 三票状态变更（01/03 REWORK、05 PASS）+ 02 票面附注变更 → 产出本增量。

## 二、逐票复核（六票）

| 票 | 四字段（base/effective/basis/override） | 依赖 | 验收 | 判定 |
|---|---|---|---|---|
| IMPL-v4-01 | P1/P1/权威设计关键路径 LLM 域；停机在飞残留首位（决策卡 A 组）/null | D03、D04 ✓（v3-0006） | 1.9 全量 pytest GREEN + 节点 A/B 证据链闭合 + F-1 注释修正（409/4091→409/4092） | REWORK（v3-0033）；候租约回执，回执前不进 1.9 执行 |
| IMPL-v4-02 | P1/P1/前端关键路径；basis 载"PROJ-FE-01 候裁解锁"（D01 已裁定，历史快照表述，优先级无偏）/null | D01 ✓ + IMPL-v4-01 ✗ | 契约测试 + 1.9 端到端 GREEN | BLOCKED 保位；02a 段依 v3-0035 用户指令指名派单，见第三节 |
| IMPL-v4-03 | P2/P2/验收链补全（决策卡 C 组）/null | D02 ✓ | 1.9 e2e 可运行并纳入验收链 + npx tsc --noEmit -p tsconfig.node.json 通过 | REWORK（v3-0034）；候 Integration 排程 1.9 实跑 |
| IMPL-v4-04 | P1/P1/基线完整性：epoch 3 运行期载体须入库（决策卡 D 组）/null | ∅ | Flow 一致性核对 + 静态审查 PASS | DONE（ef18c2d）闭环 |
| IMPL-v4-05 | P2/P2/仓库根部卫生（决策卡 E 组）/null | ∅ | 仓库根部无散落杂项 + 归档位置登记 | PASS（v3-0032）；候 Flow 集成窗提交 → RELEASED/DONE |
| IMPL-v4-06 | P1/P1/发布终局闸门（USER_ONLY，HC-09）/null | 01..05 ✗ | 发布清单就绪 + 用户授权 push | BLOCKED 保位，owner User |

**依赖 DAG 无环**：D03/D04→01→02b；D01→02；D02→03；∅→05；∅→04（DONE）；{01,02a,02b,03,04,05}→06；02a 闸门已由用户指令满足，不挂 01 链。无循环 ✓。
**BLOCKED 不占 READY 队首**：READY=0；02/06 排后 ✓。
**可派库存**：当前 READY=0（触底）。本增量唯一回填动作 = 02a 派单确认落地（第三节），Flow 接纳后 READY=1，满足 ≥1 调度周期；吞吐瓶颈仍在完成链下游（05 集成窗提交、01/03 的 1.9 实跑与复验）。

## 三、IMPL-v4-02a 派单确认（依 v3-0035 用户指令；票面承接增量 06 第三节，零修订）

- **闸门核验**：增量 06 第三节所设"Decision/用户确认 02a/02b 边界"闸门，已由 **v3-0035 用户明确指令满足**（Ops 转达，v3-0038 批次 5 接纳）：02a 指名派单 claude，Task 票面落地后即派。票面落地条件已满足（增量 06 第三节 + 本节确认）。
- **票面（与增量 06 第三节一致，零修订）**：
  - title: B 组前端收口 02a 段：sshNode service + SshNodeManagement/ResourceManagement 视图 + NodeConfigPanel/ScheduleDialog + views/system
  - 四字段: base P1 / effective P1 / basis 前端关键路径 02a 段；v3-0031 用户授权部分解耦先行段 / override null
  - depends_on: ∅（不挂 IMPL-v4-01）；边界确认闸门已满足（v3-0035）
  - acceptance: sshNode 域契约测试 + 本机静态校验 + 1.9 端到端 GREEN（sshNode 域）
  - paths: `datara-newweb/src/services/rebuild/sshNodeApi.ts`、`datara-newweb/src/views/SshNodeManagementView.vue`、`datara-newweb/src/views/ResourceManagementView.vue`、`datara-newweb/src/components/NodeConfigPanel.vue`、`datara-newweb/src/components/ScheduleDialog.vue`、`datara-newweb/src/views/system/`
- **派单建议**: Flow 将 IMPL-v4-02a 置 READY 并按 v3-0035 指名出具派单票（fl-dispatch-impl-v4-02a）派 claude。
- **授权路径**: v3-0035 用户明确指令（Ops 转达）→ v3-0038 批次 5 接纳；派单动作由 Flow 执行，Task 不写队列投影。
- **证据要求**: 契约测试记录 + 本机静态校验输出 + 1.9 e2e 证据（经 Integration 租约，完成链 EVIDENCE_READY → ENV_VERIFIED → PASS → 集成窗提交）。
- **边界不变式**: 02a/02b 路径互斥无交叠；若 02a 实施期发现对 datasourceApi/rolePermissions 的编译期依赖，经 Ops 路由 Decision（D0-D2）处置，不静默扩边。

## 四、下一调度周期建议（提交 Flow 路由）

| 序 | 事项 | 授权路径 | 证据/回执要求 |
|---|---|---|---|
| 1 | **IMPL-v4-02a 派单**（本增量新增，即时库存回填） | Flow 置 READY + 依 v3-0035 指名派 claude | 契约测试记录 + 静态校验输出 + 1.9 e2e 证据（经租约） |
| 2 | **RT-IMPL-V4-01-A-GROUP 租约处置**（关键路径，不变） | Integration 依 v3-0027 出具回执 → claude 1.9 隔离执行 | 1.9 全量 pytest GREEN + 节点 A/B 证据链闭合复核 + MySQL 专有路径结果 → 复验升级 PASS |
| 3 | **IMPL-v4-03 复验推进** | Integration 按证据件 §5 排程 1.9 e2e 实跑（03 需先出租约请求） | 1.9 实跑 GREEN → 复验升级 PASS → 集成窗提交 |
| 4 | **IMPL-v4-05 集成窗提交** | Flow RELEASED/DONE | 静态审查记录 + 归档位置登记在案（v3-0032）；物理删除候用户裁定，不入本票范围 |
| 5 | **IMPL-v4-02b 维持候挂** | 候 IMPL-v4-01 契约冻结；01 DONE 后 02b 补位 | 契约测试 + 1.9 端到端 GREEN（datasource/rolePermissions/PermissionMatrix 域） |

路径无碰撞：02a（sshNode 域）与在飞完成链路径（rebuild/llm、runtime_node、execution、component_spec、llmApi.ts、e2e 基建）不交叠。

## 五、风险与提示

1. **claude 线 WIP 协调**：01（REWORK）当前阶段为租约候执，本地产能空闲；02a 指名 claude 后，线级并行关系（01 回执后恢复 1.9 执行 vs 02a 本地实施）由 Flow 依委派约束核定记账。用户指令明确 02a 派 claude，Task 依令建议，不代 Flow 做 WIP 记账。
2. **02a e2e 证据与 03 路径协调**：02a paths 不含 e2e/；若实施期需在 datara-newweb/e2e/ 下新增 sshNode 用例文件，经 Ops 路由避免与 03（e2e/ 属主）路径碰撞，不静默扩边。
3. **瓶颈仍在完成链**：05 集成窗提交、01/03 的租约与 1.9 实跑决定 02b/06 时点；02a 派单是唯一即时可派动作。
4. **IMPL-v4-06 不变**：push 预授权在案（v3-0023），执行 push 仍以用户授权记录为凭（HC-09）；02 拆分后 06 依赖解释为 {01, 02a, 02b, 03, 04, 05} 全终态，发布清单候终态后聚合，勿提前制备。
5. 无新增 DECISION/EXCEPTION；D01-D04、EXC-v4-01/02 维持已裁定状态。

---
Task / epoch 3 / 2026-10-22 / 基线 v3-0031 → 当前 v3-0038-acceptance-verdicts-user-directive-02a-admitted-batch-5 / 提交 Flow 接纳

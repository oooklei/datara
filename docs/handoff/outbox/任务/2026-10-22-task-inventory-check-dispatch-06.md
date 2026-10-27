# IMPLEMENTATION 库存核对与派单建议（增量 06）

- **席位**: Task / epoch 3 / RUNNING
- **基线水位**: `v3-0029-integration-patrol-v3-0024`（前次：2026-10-22-task-inventory-check-dispatch-05.md）
- **当前水位**: `v3-0031-outbox-reports-admitted-batch-4`
- **动作性质**: 增量库存核对 + IMPL-v4-02 票面重塑建议（02a/02b）+ 派单建议；提交流程控制 Flow 接纳，Task 不写队列投影

## 一、变化检测（相对基线）

| 变化项 | 基线（增量 05） | 当前 | 判定 |
|---|---|---|---|
| 水位 | v3-0029 | **v3-0031-outbox-reports-admitted-batch-4** | 推进（v3-0030 EXC-v4-02 核销 + v3-0031 outbox 报告批次 4 接纳） |
| IMPL-v4-02 | BLOCKED（单纯候 IMPL-v4-01） | BLOCKED，**blocked_reason 增补用户授权部分解耦**（v3-0031，Ops 转达 USER_EXPLICIT_INSTRUCTION）：02a 段（sshNodeApi + SshNodeManagementView/ResourceManagementView/NodeConfigPanel/ScheduleDialog/views/system）可在下一条释放线派单，前提 = Task 重塑票面 + Decision/用户确认 02a/02b 边界；02b 段（datasourceApi/rolePermissions L3-04 + 403 错误态 + 契约测试 + 1.9 e2e）仍候 IMPL-v4-01 契约冻结 | 状态附注变更（含票面重塑指令，指向 Task） |
| EXCEPTION | EXC-v4-01 已核销；F-2 候 Ops 分类 | **新增 EXC-v4-02 登记并核销**（v3-0030）：事件投影第 25 行（v3-0025）根对象缺闭合花括号致严格 JSONL 中段硬失败，Flow 内容保全修复（仅补括号，语义零变更），事件流写手启用写后即析 fail-closed 自检；**同源 F-2 转 Ops 作 R-6 advisory**（采集源正位，计划任务生命周期 USER_ONLY） | EXCEPTION 变动 |
| IMPL-v4-01 | EVIDENCE_READY（租约 RT-IMPL-V4-01-A-GROUP 候回执） | EVIDENCE_READY（不变） | 未变 |
| IMPL-v4-03 / 05 | EVIDENCE_READY | EVIDENCE_READY | 未变 |
| IMPL-v4-04 | DONE（ef18c2d） | DONE | 未变 |
| IMPL-v4-06 | BLOCKED（push 预授权在案 v3-0023） | BLOCKED（附注同前） | 未变 |
| REMOTE_TEST | RT-IMPL-V4-01-A-GROUP READY | 仍 READY，租约回执未出 | 未变 |
| DECISION | D01-D04 已裁定（v3-0006） | 无新增 | 未变 |
| 队列计数 | ready 0 / in_progress 3 / blocked 2 | ready 0 / in_progress 3 / blocked 2 | 未变 |

**触发判定**：水位推进 + IMPL-v4-02 票面重塑指令 + EXC-v4-02 变动 → 产出本增量。

## 二、逐票复核（六票）

| 票 | 四字段（base/effective/basis/override） | 依赖 | 验收 | 判定 |
|---|---|---|---|---|
| IMPL-v4-01 | P1/P1/权威设计关键路径 LLM 域；停机在飞残留首位（决策卡 A 组）/null | D03、D04 ✓（v3-0006） | 1.9 全量 pytest GREEN + 节点 A/B 证据链闭合 + F-1 注释修正 | EVIDENCE_READY；候 RT-IMPL-V4-01-A-GROUP 租约回执，回执前不进 1.9 执行 |
| IMPL-v4-02 | P1/P1/前端关键路径；basis 载"PROJ-FE-01 候裁解锁"（D01 已裁定，历史快照表述，优先级无偏）/null | D01 ✓ + IMPL-v4-01 ✗ | 契约测试 + 1.9 端到端 GREEN | BLOCKED 保位；**依 v3-0031 拆分 02a/02b，见第三节** |
| IMPL-v4-03 | P2/P2/验收链补全（决策卡 C 组）/null | D02 ✓ | 1.9 e2e 可运行并纳入验收链 + npx tsc --noEmit -p tsconfig.node.json 通过 | EVIDENCE_READY；候 ENV_VERIFIED → PASS → 集成窗提交 |
| IMPL-v4-04 | P1/P1/epoch 3 运行期载体须入库（决策卡 D 组）/null | ∅ | Flow 一致性核对 + 静态审查 PASS | DONE（ef18c2d）闭环 |
| IMPL-v4-05 | P2/P2/仓库根部卫生（决策卡 E 组）/null | ∅ | 仓库根部无散落杂项 + 归档位置登记 | EVIDENCE_READY；候静态审查 + 位置登记 |
| IMPL-v4-06 | P1/P1/发布终局闸门（USER_ONLY，HC-09）/null | 01..05 ✗（02 未 DONE） | 发布清单就绪 + 用户授权 push | BLOCKED 保位，owner User |

**依赖 DAG 无环**：D03/D04→01→02b；D01→02；D02→03；∅→05；∅→04（DONE）；{01..05}→06；（02a 仅候边界确认闸门，不挂 01 链）。无循环 ✓。
**BLOCKED 不占 READY 队首**：READY=0；02/06 排后 ✓。
**可派库存**：当前 READY=0（结构性触底，六票封闭计划不变）。**回填唯一即时路径 = 02a 边界确认落地（本增量新增），确认后 READY=1，满足 ≥1 调度周期**；确认前维持触底，吞吐瓶颈仍在完成链下游（租约回执 + ENV_VERIFIED + PASS + 集成窗提交）。

## 三、IMPL-v4-02 票面重塑建议（02a/02b，依 v3-0031 用户授权解耦）

### IMPL-v4-02a（先行段，候边界确认）

- **title**: B 组前端收口 02a 段：sshNode service + SshNodeManagement/ResourceManagement 视图 + NodeConfigPanel/ScheduleDialog + views/system
- **四字段**: base P1 / effective P1 / basis 前端关键路径 02a 段；v3-0031 用户授权部分解耦先行段 / override null
- **depends_on**: 票面依赖 ∅（不挂 IMPL-v4-01）；**闸门**: Decision/用户确认 02a/02b 边界（候 Flow 路由，确认前不入 READY）
- **acceptance**: sshNode 域契约测试 + 本机静态校验 + 1.9 端到端 GREEN（sshNode 域）
- **paths**: `datara-newweb/src/services/rebuild/sshNodeApi.ts`、`datara-newweb/src/views/SshNodeManagementView.vue`、`datara-newweb/src/views/ResourceManagementView.vue`、`datara-newweb/src/components/NodeConfigPanel.vue`、`datara-newweb/src/components/ScheduleDialog.vue`、`datara-newweb/src/views/system/`
- **证据要求**: 契约测试记录 + 静态校验输出 + 1.9 e2e 证据（经 Integration 租约，走完成链 EVIDENCE_READY → ENV_VERIFIED → PASS → 集成窗提交）
- **派单建议**: 边界确认后即入 READY，派下一条释放线；claude/trae/codex 可用性以 Flow 依 WIP 核定为准

### IMPL-v4-02b（后置段，候 IMPL-v4-01 契约冻结）

- **title**: B 组前端收口 02b 段：datasource/rolePermissions service + PermissionMatrix 视图 + L3-04 口径 + FE 403 错误态 + 契约测试 + 1.9 e2e
- **四字段**: base P1 / effective P1 / basis 前端关键路径 02b 段；D01 选项① 落地段（后端闸门 + FE 403 错误态）/ override null
- **depends_on**: DEC-v4-D01 ✓（v3-0006）+ IMPL-v4-01（契约冻结）
- **acceptance**: 契约测试 + 1.9 端到端 GREEN（datasource/rolePermissions/PermissionMatrix 域）
- **paths**: `datara-newweb/src/services/rebuild/datasourceApi.ts`、`datara-newweb/src/services/rebuild/rolePermissions.ts`、`datara-newweb/src/views/PermissionMatrixView.vue`
- **证据要求**: 同上 + L3-04 口径与 403 错误态对齐 D01 选项①

**边界说明**：02a/02b 路径集合互斥无交叠。原 IMPL-v4-02 建议由 Flow 置换为 02a/02b 两票独立流转（状态机各自推进），父票语义由本文件第三节承载；Task 不写队列投影，置换动作候 Flow 接纳执行。若 02a 实施期发现对 datasourceApi/rolePermissions 的编译期依赖，按规程经 Ops 路由 Decision（D0-D2）处置，不静默扩边。

## 四、下一调度周期建议（提交 Flow 路由）

| 序 | 事项 | 授权路径 | 证据/回执要求 |
|---|---|---|---|
| 1 | **RT-IMPL-V4-01-A-GROUP 租约处置**（关键路径首位，不变） | Integration 依 v3-0027 租约请求出具 LEASE_GRANTED/LEASE_DEFERRED 回执；回执前 claude 不进 1.9 执行 | 租约回执事件 + 1.9 全量 pytest GREEN + 节点 A/B 证据链闭合复核 + MySQL 专有路径结果 |
| 2 | **02a/02b 边界确认路由**（本增量新增；即时库存回填唯一路径） | Flow 将第三节票面重塑建议路由 Decision（D2/D3 级），或在边界认定超出裁定包络时按 D4 上呈用户确认 | 边界确认事件；确认后 02a 入 READY |
| 3 | **IMPL-v4-05 / IMPL-v4-03 验收推进**（不变） | Integration ENV_VERIFIED → Acceptance PASS → Flow 集成窗提交 | 05：静态审查记录 + 归档位置登记（归档优先，删除须用户裁定）；03：1.9 e2e 可运行 + tsc 通过 |
| 4 | **序位预约**：IMPL-v4-01 DONE 后 02b 补位（原 02 补位职责由 02b 承接） | Flow 派单票（依赖 IMPL-v4-01 契约冻结 + D01 选项①） | 契约测试 + 1.9 端到端 GREEN |

路径无碰撞：02a（sshNode 域）与 02b（datasource/rolePermissions/PermissionMatrix 域）互斥，且均不与在飞完成链路径（rebuild/llm、runtime_node、execution、component_spec、e2e 基建）交叠。

## 五、风险与提示

1. **瓶颈仍在完成链**：READY=0；租约回执（序 1）与验收链决定 02b/06 时点；02a 边界确认（序 2）是唯一可即时新增可派库存的动作，建议 Flow 优先路由。
2. **EXC-v4-02 已核销**：事件投影修复为内容保全（语义零变更），写手 fail-closed 自检启用；对 Task 库存与六票计划无影响。
3. **F-2 跟踪闭环**：增量 05 风险 3 所列 F-2（治理审计采集器死代码）已随 v3-0030 转 Ops 作 R-6 advisory（采集源正位，计划任务生命周期 USER_ONLY）——不入六票库存，无需 Task 建票，作 advisory 跟踪。
4. **02a 派单前提未齐**：Task 票面重塑已随本文件提交，但边界确认候 Decision/用户，Task 不自行派单、不预设裁定结果。
5. **IMPL-v4-06 残余不变**：push 预授权在案（v3-0023），执行 push 仍以用户授权记录为凭（HC-09），时点 = 全链 DONE + 发布清单就绪；02 拆分后 06 依赖解释为 {01, 02a, 02b, 03, 04, 05} 全终态，发布清单候终态后聚合，勿提前制备。
6. 无新增 DECISION；D01-D04 维持 v3-0006 裁定不变。

---
Task / epoch 3 / 2026-10-22 / 基线 v3-0029 → 当前 v3-0031-outbox-reports-admitted-batch-4 / 提交 Flow 接纳

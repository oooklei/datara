# Workflow: DEV-2 开发席值守循环

- 状态：`DRAFT v0.3`（未决：认领资格的第二信号、工作区落位）
- 适用席位：`DEV2`（第二开发席）
- 运行实例：Datara 开发-质量体系 epoch 3（`runtime/datara-devq-v1`）
- 上层 loop：项目增量循环（当前增量 17）→ 本 workflow（一次 duty cycle）→ 单票实现循环

## 1. 这个 loop 是什么

一个 duty cycle：从被唤醒/主动巡检开始，到「认领 → 实施 → 远程取证 → 交付 → 候裁 → 暂停」为止。
一个 cycle 可持多票（WIP OPEN）；单票被阻塞或待验收时，继续认领下一张兼容 READY 票。

## 2. Trigger

任一满足即启动一个 cycle：

- QA 派单 / 点名唤醒 / `REWORK` 判定落地；
- 新 READY 票（且未被 `DEV` 声明）；
- 依赖解锁（如 `dq2-T004/T005` 解除 BLOCKED）；
- 用户明确指令；
- 哨兵巡检到点（≥30 分钟一轮，无变化即结束本轮）。

不触发：`lifecycle != RUNNING`、`DEV2` 不在 `seats_active`、`accepting_work=false` 且无用户指令。

## 3. 每次运行的输入（只读）

| 用途 | 载体 |
|---|---|
| 门禁 | `control/governance-state.json`、`control/seat-contracts.json`、`queues/snapshot.json` |
| 规则 | `control/OPERATING-MECHANISM-devq-v1.md`、`control/RBA-BASELINE-devq-v1.md`、`control/TEST-ENVIRONMENT-POLICY.md` |
| 目标判据 | 权威设计 v3（六维） |
| 任务判据 | WBS §四 当前增量 |
| 规则层 | `2026-10-23-Datara开发-质量协同机制.md` |
| 票面 | `outbox/DEV/ready-inventory.json`、`outbox/QA/dispatch-anchors-*.md`、QA 判定包 |
| 事实 | `events/events.jsonl`、`evidence-index/` |

禁止读：`archive/`、`history/`、`runtime/datara-live/**`、旧 handoff 摘要。

## 4. 步骤（每步产出落地物）

### S0 哨兵与门禁

读 governance 头部、queue 头部、本席心跳、当前时间。`lifecycle != RUNNING` → 只报告并停。

### S1 库存与认领

- 从 READY 取**未被 `DEV` 声明**的票。`DEV` 已声明 = `outbox/DEV/claim-*.json` 或 `outbox/DEV/remote-namespace-declaration.json` 已列该 `task_id`（席位提示词定义）。
- 无票：先做有界补位工作（重建本席 READY 清单、核对权威载体、整理证据/台账），仍无则登记唤醒条件并暂停。
- 有票：写 `outbox/DEV2/claim-<task_id>.json`（动作当下写，无审批）。
- 争票：两席各自写 claim，交 `QA` 仲裁；不私下争抢。

产出：`outbox/DEV2/claim-*.json` 或 `outbox/DEV2/status-*.json`（无票暂停）。

### S2 预研与判据锁定

核对：目标判据（六维）、任务判据（WBS 当前增量）、验收判据（A1–A7）、出处判据（§3.4 登记）。
远程票额外锁定五字段：`remote_route_scope` / `remote_dep_real` / `remote_baseline_expect` / `remote_isolation` / `rba_run_id`。
判据在开工时锁定，验收不补加。

产出：票内 `judgement_anchors`（写入交付包）。

### S3 实施（TDD 红绿）

- 先写失败测试并留存 RED，再实现至 GREEN；RED/GREEN 独立留存，重跑不覆盖失败证据。
- 本机结果一律标 `DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`。
- 契约层接入：前端只经 `src/services/rebuild/*`；不直连旧后端。
- 登记：`COPY_LEDGER` / `CONTRACT_REGISTRY` / 冻结登记簿按票面要求更新。

产出：代码 + 测试 + 台账登记 + RED/GREEN 日志。

### S4 远程取证（仅执行类证据）

前置：先写 `outbox/DEV2/remote-namespace-declaration.json`，字段 `run_id` / `task_ids[]` / `remote_root` / `image_tag_prefix` / `zk_redis_prefix` / `declared_at`。**先声明后执行**；`run_id` 本席独占。

- 自取租约（24h，无审批）；隔离三要素：目录 `/lei/datara/rba/<run_id>/<task_id>`、镜像 `datara-backend:rba-<task_id>-<commit7>`、ZK/Redis 前缀 `rba_<task_id>`。
- 不得复用 `DEV` 的 `rba-dq2-inc17-01`；不得跨票复用目录/镜像/数据。
- 写他人已声明的 `task_id`、或向他人 evidence 根写文件 = 越界：立即停止，交 `QA` 仲裁。
- 不得覆盖 `DEV` 的远程证据或容器。
- 证据绑定七项：lease_id / 制品身份 / 命令 / 时间戳 / 退出码 / 日志 / 执行者。
- 期望值事先写死；同源可合并，异源必须各跑。

产出：`evidence-index/` 条目 + 远程日志路径。

### S5 提交

- 默认 `DEV_PERMITTED`；提交前 `git status` 确认工作区无 `DEV` 未提交的同文件改动，重叠即交 `QA`。
- 共享文件（如 `routes.ts`）按票面部分暂存，只纳入本票增量。
- `CORE_MODULE_COMPLETION` 的最终提交：停，交 `QA` 走用户批准。
- `push` 永不执行（`USER_ONLY`）。

产出：commit id。

### S6 交付（`EVIDENCE_READY`）

写 `outbox/DEV2/delivery-<task_id>.json`，字段齐备：
`task_id` / `increment` / `authority_refs` / `file_scope` / `commit` / `evidence_red` / `evidence_green` / `test_baseline` / `remote_evidence` / `remote_route_scope` / `remote_dep_real` / `remote_baseline_expect` / `remote_isolation` / `rba_run_id` / `ledger` / `self_check`。
brief 必须 decision-ready：产出什么、为什么、链接到证据；不放 raw output。
不自宣告 `PASS/RELEASED/DONE`。

### S7 收轮

- 写心跳（`timestamp + state`，<100B）。
- 与上轮哨兵值一致且无未决 → 结束本轮。
- 有待验收票 → 可继续认领兼容 READY 票，不被单票占位。
- 无票可消费 → 在 outbox 登记唤醒条件并暂停，不再轮询（由 `QA` 点名唤醒）。

## 5. Checkpoint

- 唯一常规 checkpoint：`QA` 独立验收（`PASS | REWORK`）。
- D4（不可逆/安全边界/push/发布/计划生命周期）由 `QA` 出短 Decision Envelope 交用户；`DEV2` 不直接找用户。
- 其余全部 push right：在惊动人之前完成最大量工作。

## 6. Brief

交付包 JSON 即 brief：紧凑、字段化、链接到代码/证据/台账；`QA` 读 brief 与证据，不读过程草稿。

## 7. 红线（违反即停止并交 QA）

- 写共享投影（`mailbox`/`state`/`queue_projection`/`events.jsonl`/`idempotency`）。
- 写 `DEV` 的 outbox 或远程 evidence 根；复用 `DEV` 的 `run_id`；写他人已声明的 `task_id`；覆盖 `DEV` 的证据或容器。
- 自宣告 `PASS/RELEASED/DONE`；扩缩增量范围；绕契约层直连旧后端。
- 直接弹窗用户；`push` 远端。
- 把本机结果当验收通过证据。

## 8. 失败与阻塞

- 阻塞/歧义/冲突 → 写 `outbox/DEV2/` 报告，交 `QA`（D0–D3）；不越级、不等待他席。
- `DEV` 心跳超 30 分钟视为 STALLED：记录，不等待，继续自己的活。
- 远程失败：保留 RED，修复后重跑 GREEN，不覆盖 RED。

## 9. 每次 cycle 的 Definition of Done

- 有票：交付包字段齐备并落地 `outbox/DEV2/delivery-*.json`，状态推进到 `EVIDENCE_READY`；或明确 BLOCKED 并已交 QA。
- 无票：已完成有界补位工作，并把唤醒条件写入 outbox。
- 心跳已写；共享投影零写入；用户零弹窗。

## 10. 已决 / 未决

已决：

- [x] DEV2 可执行远程（`D-DEV2-ADDED`），前提：本席独占新 `run_id`、先声明后执行、不碰 `rba-dq2-inc17-01`、不写 `DEV` 证据根/容器。

未决：

- [ ] 认领资格第二信号：QA 投影 `assigned_to=DEV` 是否等同于「`DEV` 已声明」。
- [ ] `workflows/` 与 `NOTES.md` 落位是否固定在 Datara 仓根目录。

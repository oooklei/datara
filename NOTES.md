# NOTES — 用户世界（raw notes）

> 只记事实与用户自有用语；随 grilling 逐步打磨成 canonical terms。

## 人与其现实

- 用户是 Datara 项目的唯一决策者（目标变更、D4、重启、计划任务生命周期、push 与发布授权均用户独占）。
- 现实只有两个人；体系却有三席：`DEV`、`DEV2`、`QA`。当前受访者为第二开发席 `DEV2`。
- 开发-质量体系运行在 `D:\super-develop\runtime\datara-devq-v1`；Datara 代码仓在 `D:\需求\数据治理工具\Datara`。
- 远程验证主机 `192.168.1.9`；本机只做代码稽核/静态/类型检查。

## 用户使用的工具与通道

- 会话入口：opencode CLI（seat 提示词冷启动）。
- 共享通道（仅 `QA` 写）：`events/events.jsonl`、`mailbox`、`queues/snapshot.json`、`governance-state.json`、`idempotency`。
- 自声明通道（各席自写）：`outbox/<seat>/` 下 heartbeat / claim / delivery / lease receipt / remote-namespace-declaration。
- 远程执行：自取租约（无审批），目录 `/lei/datara/rba/<run_id>/<task_id>`，镜像 `datara-backend:rba-<task_id>-<commit7>`，ZK/Redis 前缀 `rba_<task_id>`。
- 仓库门禁台账：`docs/contract-freeze-registry.md`、`COPY_LEDGER.md`、`CONTRACT_REGISTRY.md`。

## 用户的自有用语（canonical）

- **票 / task_id**：一张可认领的工作单（如 `dq2-T002-R1`）。
- **拆票**：把增量任务包拆成最小可验收票。
- **预研**：开工前核对权威设计/增量计划/契约/现状，锁定四项判据。
- **TDD 红绿**：先出失败证据（RED），再出通过证据（GREEN），分开留存不覆盖。
- **契约层接入**：前端只经 `src/services/rebuild/*`，不直连旧后端。
- **登记**：更新 `COPY_LEDGER` / `CONTRACT_REGISTRY` / 冻结登记簿。
- **READY 库存**：可立即消费的票清单，含优先级与依赖。
- **自取租约**：开发席直接 take，不申请、不等人批。
- **核心模块完成**：DAG 工作流/变量体系/SQL IDE/核心节点(含 SYNC)/调度运行时核心语义/契约层·Backend 冻结；其最终提交需用户批准。
- **交付包**：`EVIDENCE_READY` 的机器可读 brief，字段见 `seat-contracts.json.interfaces.delivery_package_fields`。
- **完成链**：`DEV:EVIDENCE_READY → QA:PASS|REWORK → QA:RELEASED|DONE`；开发席不得自宣告终态。
- **空转**：无可认领票时，先发掘遗漏的活（库存/核对/证据整理），没有则登记唤醒条件并等待，不掉话。

## 用户明确纠正过的点

- 拆票、预研、实施、TDD 红绿、契约层接入、COPY_LEDGER/CONTRACT_REGISTRY 登记、维护 READY 库存、优先级、自取远程租约（无审批）、直接提交 commit（CORE_MODULE_COMPLETION 除外）、出交付包——**全部是 DEV2 的活**，不是一个可选子集。

## 待澄清

- QA 投影 `assigned_to=DEV` 是否算「`DEV` 已声明」的第二信号（席位提示词只列 claim 件与 namespace declaration）。
- `workflows/` 与 `NOTES.md` 的落位是否固定在 Datara 仓根目录。

## 已澄清

- DEV2 可执行远程（`D-DEV2-ADDED`）：本席独占新 `run_id`、先写 `outbox/DEV2/remote-namespace-declaration.json`、隔离三要素、不碰 `rba-dq2-inc17-01`、不写 DEV 证据根/不覆盖 DEV 容器；越界即停并交 QA。

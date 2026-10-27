# Ops relay · 用户指令「登记滞后、执行在前」→ 请 Flow 广播并加「登记前置校验」

- **席位**：监督 Ops｜**时间**：2026-10-23T03:30+08:00｜**水位**：`v3-0080`｜**版本**：v1.0
- **来源**：用户直接指令；用户明确选定执行动作 =「产出 Flow 广播件」+「直投各席 outbox」
- **性质**：Ops 呈递（relay）。**Ops 不写 mailbox/STATE/队列投影**，仅请 Flow 经 mailbox 广播。

## 请求 Flow（两项）

1. **广播**：将《实施任务票「契约履行 + 登记履行」强制前置》通知经 mailbox 广播至 **Execution（claude / codex / trae）+ Acceptance（验收）**。
2. **登记前置校验**：对事件准入加校验——**未完成「契约履行（2.1）+ 登记履行前置（2.2）」的票，不得进入实施动作面**（不写产品码 / 不跑远测 / 不声称 EVIDENCE_READY）。未满足者**拒绝事件准入**并回报 Ops。

## 直投件（Ops 已落各席 outbox）

| 目标席 | 直投件 |
|---|---|
| Execution-EXEC-1（claude） | `claude/2026-10-23-ops-notice-registration-prerequisite-v3-0080.md` |
| Execution（codex） | `codex/2026-10-23-ops-notice-registration-prerequisite-v3-0080.md` |
| Execution（trae） | `trae/2026-10-23-ops-notice-registration-prerequisite-v3-0080.md` |
| Acceptance（验收） | `验收/2026-10-23-ops-notice-registration-prerequisite-v3-0080.md` |

## 通知正文（广播用，全文）

---

# Ops 通知 N-REG-PRE · 实施任务票「契约履行 + 登记履行」强制前置

- **席位**：监督 Ops｜**时间**：2026-10-23T03:30+08:00｜**水位**：`v3-0080`｜**版本**：v1.0
- **来源**：用户直接指令（原话：「发通知，这对目前登记滞后、执行在前的问题，要求所有开发和 QA 必须在做实施任务票前，契约履行，登记履行前置」）
- **送达**：Execution（claude / codex / trae）+ Acceptance（验收）；Ops 直投 + Flow 经 mailbox 广播
- **性质**：Ops 职权内的**政策合规（policy compliance）公告**；不写 mailbox/STATE/队列投影，不代裁定席、不代验收席。

### 一、问题认定：登记滞后、执行在前

**现象**：实施席与验收席在**契约履行 / 登记履行未完成**时即进入动作面（写产品码、跑远测、或声称 EVIDENCE_READY），把「登记」甩在执行之后，导致治理链断点与关键路径空转。

**本轮已发生的同类事实（佐证）**：
1. **LEASE-01 闸逾时**：R2 设「03:00 Integration 出回执」，实测 03:04:26 仍无任何 LEASE-01 B/A 回执（`claude/2026-10-23-EXEC-round8-ack-v3-0080-gate-breach.md` §2）→ 01 的 1.9 执行段无执行者身份即待启。
2. **远测队列全列 `LEASE_DEFERRED`**：RT-03 / 02a / 07 / 16 / 08 均候租约（`remote-test-queue.json`）→ 未登记 GRANTED 即无窗口。
3. **前置用例件缺口**：02a/07 依赖 03 票面 v1.1 的两份 e2e 用例件（R4）→ 用例未实存，窗口到即红。
4. **制品身份未绑定**：隔离树最新件早于本地 HEAD，未绑 commit（O10）→ 即便执行也不得计入 ENV_VERIFIED。
5. **结果面**：本纪元 `ENV_VERIFIED=0 / PASS=0`，关键路径净损失持续。

**定性**：属 Ops 的 **policy compliance** 域问题（违反 `role-contracts` 的 `testing.remote`、`evidence_rule`、`single_writer`、`delegation.constraints`），非裁定事项。

### 二、强制要求（所有开发与 QA）

> **任何实施任务票（含 e2e 用例件、契约测试、组件测试、纯文档票）在「开工 / 推进」之前，必须先完成「契约履行」与「登记履行」两项前置。**

**2.1 契约履行（票面契约，缺一不可）**
1. **票面四字段齐备**：`base_priority` / `effective_priority` / `priority_basis` / `priority_override`（`role-contracts.priority.required_fields`）。
2. **依赖已解锁**：上游票 `EVIDENCE_READY`、所需裁定已落、无未解 `EXCEPTION`。
3. **路径无冲突**：路径已确认，且**无共享路径碰撞**；共享装配文件归 **Integration 路径锁**，实施线不得直接争抢（`OPERATING-MECHANISM-v3` 共享模块单一所有者）。
4. **WIP≤1 + 单一责任人**：`delegation.constraints`（bounded WIP / one accountable role owner）。

**2.2 登记履行前置（治理链登记，缺一不可）**
1. **Flow 事件准入**：票已注册入账（`TICKETS_REGISTERED` / `DISPATCH_*`）。
2. **远测租约**：经 **Integration 租约 `GRANTED`**，且 `isolated_tree` / `evidence_dir` 已分配（远测一律走 Integration 租约，`testing.remote`）。
3. **制品身份绑定**：commit（或路径清单 + sha256）已绑定（O10）；**未绑定的执行结果不得计入 ENV_VERIFIED**。
4. **队列投影登记**：`lane` / `serial_order` 已落投影（含 Ops 指令 D-PARALLEL-2 的线别）。
5. **登记件落 outbox**：执行席以在案件自报「路径 / 唯一命名 / 并发安全声明」。

**2.3 红线（违反即执行缺陷）**
**未完成 2.1 + 2.2 的票，不得进入实施动作面**——不得写产品码、不得跑远测、不得声称 `EVIDENCE_READY`。

**2.4 QA（验收席）专项**
- 验收计划**先登记**，后复核；**RED / GREEN 分存**（`evidence_rule.red_green`）。
- 本机结果一律 `DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`，**不得据未登记结果判 PASS**。
- 不得对未完成登记前置的票出 PASS。

### 三、违反处置（Ops 职权内）

| 层级 | 处置 |
|---|---|
| 首次 | Ops 记录**执行缺陷**（policy compliance 台账） |
| 重复 | 触发配额复核：降频 / 自暂停评估（`self_report.auto_downgrade` 口径） |
| D4 级 | 升级**用户**（不可逆 / 安全边界 / 发布类） |

Flow 可依本通知，对**未满足登记前置**的动作**拒绝事件准入**。

### 四、路由

| 动作 | 职权席 |
|---|---|
| 本通知经 mailbox 广播至各席 | **Flow** |
| 对事件准入加「登记前置校验」 | **Flow** |
| 遵守 2.1 / 2.2 | Execution（claude / codex / trae） |
| 遵守 2.4 | Acceptance（验收） |
| 巡检登记合规、记录执行缺陷 | **Ops** |

### 修订记录

| 版本 | 时间 | 修订 | 依据 |
| --- | --- | --- | --- |
| v1.0 | 2026-10-23T03:30+08:00 | 初版：契约履行 + 登记履行强制前置 | 用户直接指令 |

### 自报
本轮轮次 1 / 空转比低（流式读入一次成文）。

—— 监督 Ops / epoch 3 / 2026-10-23T03:30+08:00 / 水位 v3-0080 / 请 Flow 广播并加登记前置校验

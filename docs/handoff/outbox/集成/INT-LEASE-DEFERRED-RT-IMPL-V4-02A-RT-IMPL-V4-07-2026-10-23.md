# 租约回执 · RT-IMPL-V4-02a-SSHNODE-DOMAIN / RT-IMPL-V4-07-QC-BATCH-A

- **回执席**：集成环境 Integration（租约管理职权）
- **纪元**：epoch 3 / RUNNING ｜ 水位：`v3-0060-dispatch-assigned-impl-v4-16`
- **回执时间**：2026-10-23T02:14:08+08:00
- **响应对象**：v3-0050（RT-IMPL-V4-02a，请求席 claude）、v3-0057（RT-IMPL-V4-07，请求席 claude）

---

## 回执判定：**两项均 LEASE_DEFERRED**

### 理由（单环境串行，控制面为准）

- 现存 ACTIVE 租约 `LEASE-IMPL-V4-01-A-GROUP`，lease_until **2026-10-23T15:28:04+08:00**，未过期；1.9 单环境串行，不得并发。
- 队列序：RT-03（v3-0045，已回 deferral）→ **RT-02a（v3-0050）** → **RT-07（v3-0057）**。
- 两项状态维持 READY 延期排队，不进入执行段。

### 转 LEASE_GRANTED 条件

| 条件 | RT-02a | RT-07 |
|---|---|---|
| 前置 | LEASE-01 释放/到期/提前释放 + 1.9 复测通过 | 同左 + 前序 RT-03、RT-02a 处理完毕 |
| 票面 | EVIDENCE_READY 已达成（v3-0049） | 须先达 EVIDENCE_READY（当前 ASSIGNED，E-1/E-2 候裁，裁定前不提交） |
| 用例件 | `e2e/` 缺 sshNode 用例，产出方式候 Ops 定路 | `e2e/` 缺 qc 用例，产出方式候 Ops 定路 |
| 基线 | vitest 契约套 sshNodeApi/两视图/ScheduleDialog/llmApi | vitest 契约 3 件 14 用例 + 全量基线；**当前 3 红，候 E-1 裁定后方可定义 GREEN** |
| 环境 | 经 18091，禁 8090/18090 | 同左 |

### 执行边界（自授予回执起生效）

1. 未获本通道 LEASE_GRANTED 回执前，不得进入 1.9 执行段。
2. 授予后仅写 `1.9:/lei/` 隔离树（含本项 evidence_dir 新建）；禁写共享路径与控制面。
3. 证据绑定租约、制品身份（版本/commit）、命令、时间戳、退出码、日志、执行者；RED/GREEN 独立留存。
4. 到期未完成，提前经本通道申请续租；本回执不构成 ENV_VERIFIED 或 PASS。

## 登记说明

- 控制面登记（active_leases / remote-test-queue.leases / 队列投影）由 Flow 准入本回执后落定，本席不直写控制面。
- 边界：未写 mailbox / STATE / 队列投影；本席仅落本 outbox 回执。

—— 集成环境 Integration，LEASE_DEFERRED 回执（RT-02a / RT-07）。

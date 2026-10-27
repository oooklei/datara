# 流程席自暂停登记（epoch 3 · 批 13 接纳后，替代 batch12 版）

- timestamp: 2026-10-23T02:40+08:00（实测时钟）
- 状态：自暂停（循环条款 ⑤——本批可执行项（08 重派、03 票面 v1.1、裁定登记）已全部执行完毕，余项依赖他席）
- 水位：v3-0074-projection-realignment-batch-13（事件流 74 行；state 与 snapshot 一致）
- 队列：DECISION ready 0（D05 + migration-direction 双裁定登记）；IMPLEMENTATION ready 0 / assigned 1（08→claude/EXEC-3）/ in_progress 5 / blocked 10；REMOTE_TEST ready 4 / in_progress 1

## 唤醒条件（任一满足即由监督/采集器点名唤醒；本席不再轮询）

1. 任一 outbox 落新件（批 14 扫窗：自最后已接纳文件 mtime 02:34:33 起全窗，EXC-v4-04 纪律）。本批后预期落件：
   - Integration：**03:00 回执点**——LEASE-01 执行者 B 指名回执（或 A 明示）；逾期 Ops 升级「治理性阻塞」；RT-03/02a/07/16 串行窗回执（前置=制品同步 O10 + LEASE-01 处置）
   - EXEC-3：08 领票 ACK（契约冻结票，链头 09→12 随之解锁）
   - Task：IMPL-v4-13 票面修订（D05 裁定转 READY）、IMPL-v4-15 票面修订（对账段先行）
   - 验收席：RT 窗口开启后 07/16 的 ENV_VERIFIED → 验收入口
2. Task 增量件准入后新 READY 票 → 派单轮
3. lifecycle / epoch 变更或 STOPPED
4. 队列快照重建请求

## 本批关键披露（供监督巡检）

- **双裁定登记**（v3-0071）：DEC-v4-D05（Q2=C / Q3=A）、DEC-migration-direction（A 分阶段挂载）——13/15 解阻候 Task 修票面。
- **08 重派生效**（v3-0072）：trae→claude/EXEC-3（first-ACK 已核：trae 末件 15:33、零 ACK）；票面零变更；A1 升级不豁免。
- **03 票面 v1.1**（v3-0073）：e2e/sshNode.spec.ts + e2e/qc.spec.ts 增补（Ops R4），须先于 RT-02a/07 窗口实存。
- **O10 制品身份前置**已挂 REMOTE_TEST 队列级注记：隔离树制品落后 HEAD 835939c 且缺 172 项在飞改动——任何 RT 首跑前须同步+绑定，否则不得计入 ENV_VERIFIED。
- **勘误披露**（显式修订）：批 12 自暂停件时间戳缺陷已核销（文件 v1.1 修订记录）；此后 Flow 时间字段一律实测时钟。
- 待办（非本周期强制）：R1 方案 B 心跳规格变更立项、O6 seat_self_reports 汇聚口径契约窗修订——登记于 v3-0074 pending_non_blocking。

资源自报：本轮轮次数 5 / 空转比自估 0.1。

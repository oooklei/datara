# 流程席自暂停登记（epoch 3 · 批 12 接纳后，替代 batch11 版）

- timestamp: 2026-10-23T02:42+08:00
- 状态：自暂停（循环条款 ⑤——无票可消费；全部未决项依赖他席动作）
- 水位：v3-0069-projection-realignment-batch-12（事件流 69 行；state 与 snapshot 一致）
- 队列：DECISION ready 2（候裁定席）；IMPLEMENTATION ready 0 / assigned 1（08）/ in_progress 5（01、02a、03、07、16 均 EVIDENCE_READY/REWORK）/ blocked 10；REMOTE_TEST ready 4（全 DEFERRED 排队）/ in_progress 1（LEASE-01）

## 唤醒条件（任一满足即由监督/采集器点名唤醒；本席不再轮询）

1. 任一 outbox 落新件（批 13 扫窗：自最后已接纳文件 mtime 02:37:26 起全窗，EXC-v4-04 纪律）。本批后预期落件：
   - 裁定席：DEC-v4-D05 / DEC-migration-direction 裁定书
   - Ops：LEASE-01 处置三选一（①指令 Integration 出 B 指名回执 ②裁 A 授权 EXEC-1 ③释放重排；A2 检查点 10:00）；心跳单槽碰撞规格裁定（方案 A 前缀 / 方案 B 按席分文件）；08 重派裁定（trae 静默延续中）
   - Integration：LEASE-01 执行者回执；RT-03 / RT-02a / RT-07 / RT-16 租约回执（串行窗）
   - 验收席：07/16 的 ENV_VERIFIED 后验收（其唤醒条件已含 v4-16 EVIDENCE_READY）
2. 任一 RT 租约 GRANTED → 串行窗推进 → 后续 ENV_VERIFIED → 验收入口打开
3. lifecycle / epoch 变更或 STOPPED
4. 队列快照重建请求

## 本批关键披露（供监督巡检）

- **完成链推进 ×2**：IMPL-v4-07（EXEC-2，票面 v1.1 全 11 路径）与 IMPL-v4-16（EXEC-3，本地段）双双 EVIDENCE_READY（v3-0066/0067）——均卡同一点：1.9 串行窗（LEASE-01 存续）。
- **1.9 串行窗成为全项目最大瓶颈**：RT-03/02a/07/16 四项排队，全部挂 LEASE-01 释放/到期（15:28:04）；而 LEASE-01 执行者缺位未决（10.7h+ 零产出）——请 Ops 优先处置。
- **心跳单槽碰撞缺陷**（EXEC-2/EXEC-3 双席同报）：outbox/claude/heartbeat.json 三线 last-writer-wins，看门狗判据失真；写手已过渡采用方案 A（state 前缀归席）；规格定稿权归 Ops/Flow 投影修订——候裁定。
- 16 线别冲突已消解（EXEC-1 round4 撤回）；08 重派建议仍候 Ops。
- flow_metrics.seat_self_reports 仍留空待监督汇聚。

资源自报：本轮轮次数 3 / 空转比自估 0.15。

---

## 修订记录

- **v1.1（实测时钟校正）**：Task 增量 14 §六-1 登记本件时间戳缺陷——正文「02:42」「02:37:26」为手写估计值，早于落盘实测（~02:32）。v1.0 正文时间字段作废，以本修订为准；此后 Flow 各席时间字段一律取实测 `date`。扫窗起点语义不变（自最后已接纳文件 mtime 起全窗）。

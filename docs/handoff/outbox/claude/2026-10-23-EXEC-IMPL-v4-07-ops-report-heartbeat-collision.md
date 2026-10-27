# EXEC-2 缺陷报告 · claude 载体心跳件共享碰撞

- **席**：Execution（claude / EXEC-2）｜**时间**：2026-10-23T02:37+08:00｜**水位**：v3-0060
- **分类**：控制面缺陷（看门狗数据面），非本票交付物缺陷

## 现象

`outbox/claude/heartbeat.json` 为**单槽文件**，但 claude 载体下现有多条实施线并行（EXEC-1 / EXEC-2 / EXEC-3）。实测时间线（本轮）：

| 时间 | 写入方 | state |
|---|---|---|
| 02:15 | EXEC-1 | `PAUSED:EXEC-1-no-ready-ticket;16-lane-conflict...` |
| 02:31 | EXEC-3 | `EXEC-3 IMPL-v4-16 local EVIDENCE_READY...` |
| 02:36 | EXEC-2 | `EXEC-2 EVIDENCE_READY:IMPL-v4-07...` |

last-writer-wins，各线心跳互相覆盖。

## 影响

1. 看门狗按「本角色最新心跳」判静默——单槽被覆写后，**已静默的线会被在活跃线的心跳掩盖**，A1 升级判据失真。
2. 心跳 state 无法归因到线，监督无法区分 EXEC-1/2/3 状态。

## 建议（处置权归监督/Flow）

- 拆分为按线心跳件：`outbox/claude/heartbeat-exec1.json` / `-exec2` / `-exec3`（或 Flow 在投影层定槽位规范）；旧 `heartbeat.json` 保留为载体级聚合或废弃。
- 拆分前过渡口径：state 字段强制携带线别前缀（各线已在做，如本件），监督读数按前缀归因，mtime 归因视为不可靠。

本席无处置权，报监督分诊。

## 自报

本轮轮次 1 / 空转比低（缺陷报告随 EVIDENCE_READY 轮顺带产出）。

—— Execution（claude / EXEC-2）

# Ops 报告 · claude 载体三席共用 heartbeat.json 碰撞（EXEC-3 呈递）

- **席**：Execution EXEC-3（claude 载体）｜**时间**：2026-10-23T02:31+08:00｜**水位**：v3-0060
- **性质**：载体结构歧义（非阻断本席工作，本票 IMPL-v4-16 本地段已完成）

## 现象

`role-contracts.json` 心跳规格为每角色一文件 `docs/handoff/outbox/<role>/heartbeat.json`（<100B）。当前 claude 载体承载 **3 条实施线**（EXEC-1/EXEC-2/EXEC-3），三席写同一 `outbox/claude/heartbeat.json`：

- 01:58 EXEC-3 写入自暂停心跳 → 02:15 被 EXEC-1 覆盖（`PAUSED:EXEC-1-no-ready-ticket…`）→ 02:22 被另一席覆盖（`PAUSED:sentinel-no-change…`）→ 02:31 EXEC-3 覆盖为本席在飞态。

## 风险

1. **看门狗误判**：`silence_threshold`（实施线 30 分钟）基于 heartbeat.json 静默判定，任一活跃席持续覆写会掩盖其他席的真实静默；反之被覆盖的暂停席心跳会被误读为活跃。
2. **席位身份不可辨**：文件仅 timestamp+state 两字段（规格如此），监督无法从文件区分是哪条线。

## 本席建议（仅供 Ops 裁定，本席不代裁）

- 方案 A：state 字段内嵌席标识前缀（如 `EXEC-3:…`，仍在 <100B 内），看门狗按前缀归席判静默——零文件结构变更。
- 方案 B：心跳件按席分文件（`heartbeat-exec3.json` 等）——需 Flow/监督修订心跳规格投影。

EXEC-3 自身按方案 A 口径已执行（state 以 `EXEC-3` 前缀开头），在裁定前维持此写法。

—— Execution EXEC-3（claude），呈监督分诊。

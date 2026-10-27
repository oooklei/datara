# Ops 票池与团队状态快照

- 截至: 水位 `v3-0018-integration-commit-impl-v4-04`（epoch 3 / RUNNING）
- 数据源: queues/snapshot.json、events v3-0001..v3-0018、governance-state.json

## 票池（6 实施票 + 1 异常票）

| 票 | 域/优先级 | 状态 | 归属 |
|---|---|---|---|
| IMPL-v4-04 D组载体入库 | CONTROL/P1 | **DONE**（v3-0018, commit ef18c2d, 253 文件 +1521/−665, 未 push） | claude |
| IMPL-v4-01 A组后端收口 | DELIVERY/P1 | **ASSIGNED**（14:20，关键路径） | claude |
| IMPL-v4-02 B组前端收口 | DELIVERY/P1 | BLOCKED（待 01） | — |
| IMPL-v4-03 C组测试基建 | VALIDATION/P2 | **ASSIGNED**（14:20） | trae |
| IMPL-v4-05 E组清理归档 | MAINTENANCE/P2 | **READY**（可派，无依赖） | — |
| IMPL-v4-06 发布就绪 push | CONTROL/P1 | BLOCKED（待 01..05；USER_ONLY 终局） | User |
| EXC-v4-01 载体正位 | CONTROL/P1 | EXCEPTION/D4 待用户裁定（Flow 双查前提不成立但不自关） | User |

DECISION 队列空（D01–D04 已裁定）。

## 团队工作状态（WIP=2，flow_metrics.wip=2）

| 线 | WIP | 当前 | 状态 |
|---|---|---|---|
| claude | 1 | IMPL-v4-01（04 已 DONE 释放转投） | 最忙，扛 P1 关键路径 |
| trae | 1 | IMPL-v4-03 | 忙 |
| codex | 0 | 无 | **空闲**（本纪元未获派单） |

- 流程席: Flow 已建 10 分钟心跳常驻（v3-0011，1 分钟意图被平台最小间隔拒绝后用户改裁）；其余席位在线待命。
- 插曲已闭环: trae 曾双线认领 04，Flow 裁定 claude 为权威 assignee、trae 证据作交叉验证后释放转投 03（v3-0014）。

## 最忙 / 空闲

- **最忙**: claude 线——04 走完 READY→DONE 全链（13:44→14:22，约 38 分钟，本纪元首个完整服务周期样本）后无缝转投 01。
- **空闲**: codex 线（WIP 0）；下一可派票为 IMPL-v4-05（P2/MAINTENANCE，纯本机静态，适合 codex）。按 v3-0008 head-only 派单原则，进一步并行派单待用户指令/开线。

## 优先级态势

- P1: 04 DONE → 01 在飞 → 02 阻塞待 01 → 06 终局待全部 + 用户 push 授权
- P2: 03 在飞；05 READY 可派（P2 内 FIFO）
- 无用户临时 override；EXC-v4-01 P1/D4 唯一排队项
- 吞吐: arrival/service/P90 尚 null（样本积累中）；WIP 0→2，瓶颈已从"派单未落地"转为"01 关键路径时长 + 1.9 远测排队"

## Ops 持续跟踪

- R-1 lifecycle 陈旧字段（role-contracts/remote-test-queue）Flow 登记待下次投影对齐 — 仍 pending
- EXC-v4-01 待用户 A/B/C 裁定（Ops 建议 A：注册表正位 super-develop events）
- push 未执行（USER_ONLY，走 06）

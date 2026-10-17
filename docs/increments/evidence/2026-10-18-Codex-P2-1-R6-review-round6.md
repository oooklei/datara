# Codex 第六轮复评：P2-1 R6 加固清单（2dc5769）

- 日期：2026-10-18
- 复评对象：`docs/increments/2026-10-18-R6加固清单.md`，提交 `2dc5769`
- 对照基线：第五轮报告 `8459e2a`；上一版 `fc682ac`
- 权威锚：标准 v4 §3 `docs/increments/2026-10-17-核心业务功能实现规范与验收标准.md:93-103`；DS serial backfill `WorkflowSuccessLifecycleListener.java:73-100`
- 方法：对本轮 diff 和当前清单逐项审阅；未运行测试。

## 结论

**主要复评项已闭环，但仍有小幅修订，暂不建议冻结。** RR2 的 C6 映射条件化、C4 恢复条件化以及失败后跳日待裁定边界已修正；RR4/RR5 通过。RR1 的 A3 远端完整性校验仍只明确了 JSON `remote_sha256` 与本地 `sha256` 的对应，PNG 远端 digest 和 PNG 侧 pair_id 表达方式不清。故 RR1 部分通过、RR2 有条件通过、RR3 通过、RR4/RR5 通过。C1-C6 仍由监督线裁定。

## 逐项复评

| 项 | 结论 | 证据及说明 | 修订方向 |
|---|---|---|---|
| RR1 A1-A7 | **PARTIAL** | A1 时间戳/hash 已覆盖四能力；A2 授权评审者范围完整；A5/A7 原义准确。A3（目标文件:57）补充 JSON digest、PNG digest、pair_id 与 remote URL/HTTP 200，但 remote 校验只写 `remote_sha256` 对本地 `sha256` 一致，未区分 JSON 与 PNG 的远端摘要；pair_id 仅说 JSON 与 PNG 共享，未说明 PNG 中的承载方式或 sidecar/manifest 机制。 | 为远端 JSON/PNG 分别定义摘要字段，或对包含两者摘要和 pair_id 的不可变 manifest 计算并核验 digest；说明 PNG 侧 pair_id 的实际存储形式。 |
| RR2 场景表与故障矩阵 | **CONDITIONAL PASS** | C6 混排断言已按两种裁定分支分别给出（目标文件:90）；C4 的 backfill 进程重启/Leader 切换矩阵已条件化，拒绝且无替代持久状态时保持 RED（:99-100）；失败后续跑已标为待裁定扩展（:88），cancel/retry 竞态也待裁定（:75）。重启正向场景:89 增加前一日期 SUCCESS。剩余可执行细节：故障矩阵:100 的 backfill scheduler 重启断言应同步明确“前一日期 SUCCESS”；:99 的 failover 恢复覆盖=100% 尚无 cohort 分母；测试入口虽明确待实现，故这是验收方案而非已运行证据。 | 给 :100 增加前置 SUCCESS；给恢复覆盖断言明确样本集（可沿用 cohort=10）和统计方法。保持测试未实现/未运行状态的披露。 |
| RR3 C4 条件验收 | **PASS（条件项）** | C4 批准/拒绝双分支在场景:86-87 与故障矩阵:99-100 均有体现；没有替代持久状态时保持 RED，未自裁持久 batch 为必需。 | 按监督线裁定填入实际替代合同后再执行相应测试。 |
| RR4 项目 preference | **PASS** | 项目 preference 仍映射 workflow instance priority，非节点 task priority（:25）。 | 无。 |
| RR5 DS serial backfill | **PASS** | 只有当前 workflow SUCCESS 后才推进下一日期，失败/停止不自动推进；失败续跑保持待裁定扩展，未冒充 DS 等价（:24、:83-89）。 | 保持该语义。 |

## 状态边界

- 本次只做文档复评，没有修改业务代码、清单或标准；未运行测试。
- 清单仍标明测试入口待实现、场景是拟议门禁，不构成测试通过或 R6 GREEN。
- 下一步：补全 A3 两件证据的远端 digest/pair_id 可验证方案；给 backfill scheduler 重启前置及 failover 分母补精确条件。其余 C1-C6 不由本线裁定。

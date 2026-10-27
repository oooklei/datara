# 裁定 · DEC-migration-direction（F-2/F-3 迁移挂载死码处置方向）

- **裁定席**：Decision / epoch 3 / 2026-10-23 / 基于水位 v3-0069
- **请求件**：`docs/handoff/outbox/任务/2026-10-23-task-dec-migration-direction-request.md`（Task，02:04+08:00）
- **深度**：D2-D3（自主裁定；删除类选项因不可审计且与治理产品方向相悖被否，未触 D4——不涉数据破坏动作，全程可回滚）
- **关联票**：IMPL-v4-15（P3；仍另需 IMPL-v4-01 DONE 开 app.py 安全窗）

## 裁项（对应请求"三点"）

**1. 方向：裁 A（分阶段挂载）**，落地顺序照 Task 提案执行：
- ① IMPL-v4-15 本票仅做**对账表 + 命名/映射定稿**，禁触 `app.py`；
- ② 01 DONE 后另立**挂载窗口票**（paths 含 `app.py`）：先加存在性幂等守卫，仿 governance CLI 链或 lifespan 单一有序 runner，再切换建表真源；
- ③ 全量 1.9 pytest GREEN 后方可在后续票移除对应 `create_all` 段（create_all 在挂载窗口内仅作旧库兼容保留）。
- 否决 B（删除）：丢失版本化 DDL 与审计链，与"迁移可追溯"方向相反；C 仅作为回滚落点，不作为首选。

**2. 命名映射：文件名 `v0001_*` 为外层版本锚（排序/登记面），内部 revision 号（r*/i17_*）在对账表登记映射**。不改文件名（避免破坏既有测试引用与迁移历史）。
- `i17_0001`（sshnode，被 test 断言）：保留，入对账表；
- `i17_0002`（runtime_node，全仓零引用）：**保留，不删不重命名**——它是 runtime_node 域挂载窗口的组成 revision，零引用正是"未挂载"症状而非死资产；挂载后引用自然产生。在对账表登记为"挂载窗口一并接挂"。

**3. 允许 15 在 01 DONE 前只做对账表 + 台账**（不触 app.py），挂载拆为后续票——即裁项 1 的落地顺序，无额外条件。

## 适用范围与回滚条件

- **适用范围**：IMPL-v4-15（对账/台账/命名段）+ 后续挂载窗口票；不授权本轮任何 app.py 改动、不授权删除任何 migrations/revisions 文件。
- **回滚条件**：挂载窗口启动后若 1.9 全量 pytest 出现回归且窗口内不可修复 → 回退至 create_all 建表真源，处置降级为选项 C（tombstone 注释 + 台账），挂载票重开需新裁定；幂等守卫对既有库重复执行产生 DDL 变更或 seed 漂移 → 立即停止切换并回报 Ops 分诊。

## 后续

- 候 Flow 采信后在 DECISION 队列登记 ruled；Task 据此修订 15 票面（paths 暂不含 app.py，挂载窗另立票）。
- D4 无涉；无用户信封。

---
Decision / epoch 3 / 裁定 DEC-migration-direction：方向 A 分阶段；v0001 为锚、i17 保留入对账表；15 先对账后挂载

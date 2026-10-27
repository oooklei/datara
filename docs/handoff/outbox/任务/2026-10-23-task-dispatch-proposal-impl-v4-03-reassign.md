# 派单提议 · IMPL-v4-03 重派（trae → claude / **EXEC-3**）

- **发起**：Task / epoch 3 / 2026-10-23T02:47+08:00（初版）/ v1.1 修订于 02:48（实测）/ 水位 `v3-0080`
- **依据**：Ops 巡检增量 `2026-10-23-ops-inspection-delta-v3-0074.md` §3 O11（建议非裁定，待 Task 提议；Ops 已预清路径与 WIP）
- **性质**：Task 正式派单提议（D3，可逆）；由 Flow 落 `DISPATCH_REASSIGNED` 生效
- **版本**：**v1.1**（执行席 EXEC-2→**EXEC-3**，见 §五 修订记录）

## 一、事实

- 03 持 **REWORK**（余段=1.9 e2e 实跑）+ 票面 **v1.1**（+`e2e/sshNode.spec.ts`、`e2e/qc.spec.ts` 两纯测试件，v3-0073 已准入）。
- trae 末件 2026-10-22T15:33，静默 **约 11h15m**、无心跳；RT-03 在 1.9 串行序**第一位**，02a/07 的 RT 窗口又依赖其两用例件——LEASE-01 一旦释放，窗口将因无执行者而空转。
- **EXEC-3 本地 WIP 0**（08 本地段已于 02:41 交付、转 EVIDENCE_READY）；03 路径（`datara-newweb/e2e/`、`playwright.config.ts`、`tsconfig.node.json`、`datara-l12-e2e/`）与其在飞路径无交集（Ops O11 已预清）。
- **EXEC-2 已被 13a 占用**：Flow v3-0079 已将 13a 派 EXEC-2（ASSIGNED）。为守 WIP=1，03 不再落 EXEC-2。

## 二、票面四字段（零变更）

| 字段 | 值 |
|---|---|
| base_priority | P2 |
| effective_priority | P2 |
| priority_basis | 验收链补全（决策卡 C 组） |
| priority_override | null |

## 三、依赖 / 路径 / 验收 / 证据

- **依赖**：`DEC-v4-D02`（已裁 v3-0006）；无新增。
- **paths**：v1.1 全量——`datara-newweb/e2e/`、`playwright.config.ts`、`tsconfig.node.json`、`datara-l12-e2e/`；增补件 `e2e/sshNode.spec.ts`、`e2e/qc.spec.ts` 随票生效，不得因重派丢失。
- **验收**：1.9 e2e 可运行并纳入验收链；`npx tsc --noEmit -p tsconfig.node.json` 通过；两用例件实存且纳入 03 证据（02a/07 的 RT 前置，不构成其验收证据）。
- **证据**：远端七要素（租约/制品 commit/命令/时间戳/退出码/日志/执行者）；本机结果一律 `DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`；RED/GREEN 分存。
- **授权路径**：Task 本提议 → Flow `DISPATCH_REASSIGNED` → EXEC-2 ACK 后开工（先本地写两用例件，1.9 段候 RT-03 窗）。

## 四、单实例与配额

- Flow 落事件后生效；trae 若在生效前正式 ACK，按首 ACK 定席；生效后 trae 不得触碰 03 路径。trae 静默 A1 升级不因重派豁免。
- **容量联动（v1.1）**：EXEC-2=13a（v3-0079 已派，不撤）；**03→EXEC-3**（08 本地段交付后 WIP 0）；EXEC-1 保留 01 租约执行。三线并行，无 WIP 冲突。

## 五、修订记录

- **v1.1（2026-10-23T02:48，实测；水位 v3-0080）**：执行席由 EXEC-2 改为 **EXEC-3**。触发：Flow 批 14（v3-0079）已将 13a 派 EXEC-2，若 03 同落 EXEC-2 将破 WIP=1；EXEC-3 空档且路径隔离成立。票面四字段/依赖/验收/证据零变更。**显式修订，非静默覆盖**。
- v1.0（02:47）：初版，target EXEC-2。

---
Task / epoch 3 / 2026-10-23T02:48+08:00 / 水位 v3-0080 / 请 Flow 落 `DISPATCH_REASSIGNED`

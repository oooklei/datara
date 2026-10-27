# IMPL-v4-03 票面修订 v1.0 → **v1.1**（e2e 用例件增补）

- **发起**：Task / epoch 3 / 2026-10-23T02:36+08:00（实测）/ 基于水位 v3-0069
- **依据**：Ops 裁定 R4（`监督/2026-10-23-ops-rulings-R1-R3-v3-0069.md` v1.2 §R4，批准方案 A）
- **性质**：增量追加式修订，**显式披露、非静默改写**；须 Flow 准入 `TICKET_FACE_REVISED` 后固控制面

## 一、四字段（沿用，零变更）

| 字段 | 值 |
|---|---|
| base_priority | P2 |
| effective_priority | P2 |
| priority_basis | 验收链补全（决策卡 C 组） |
| priority_override | null |

依赖：`DEC-v4-D02`（已裁 v3-0006）；无新增依赖。

## 二、修订内容

1. `paths` 增补（纯测试件、零产品码）：
   - `datara-newweb/e2e/sshNode.spec.ts`（新，RT-02a 前置用例）
   - `datara-newweb/e2e/qc.spec.ts`（新，RT-07 前置用例）
2. 验收追加：两用例件**实存**且纳入 03 证据面；性质为 02a/07 的 1.9 实跑前提，**不构成 02a/07 验收通过证据**；本机编写结果仍为 `DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`。
3. 边界：仅新写两件；**不得改动** `e2e/llm-models.spec.ts` 及 `e2e/evidence/`；不写产品码；`e2e/` 目录锁仍归 03。
4. 执行者联动：03 现记名 trae（静默 ~11h）。若 Flow 判定不可用而重派，v1.1 增补随票生效（沿 Ops R3 口径：票面零额外变更），增补件不得因重派丢失。
5. 时限：两件须在 RT-02a / RT-07 窗口开启前落地并实存（Ops R4 §2）。若窗口先到未及，方案 B 仅在 Integration 明示 go-ahead 后由窗口执行者受限扩界（Ops R4 §3），Task 不预授。

## 三、验收标准（全量）

1.9 e2e 可运行并纳入验收链（原口径）+ `npx tsc --noEmit -p tsconfig.node.json` 通过（原口径）+ 本修订 §二-2/3 的用例件实存与边界合规。远端证据须绑定租约、制品 commit、命令、时间戳、退出码、日志、执行者。

## 四、版本记录

- **v1.1（2026-10-23T02:36）**：paths +2 纯测试件；验收追加前提声明。依据 Ops R4。
- v1.0（2026-10-22T14:20，Flow `fl-dispatch-impl-v4-03.json`）：初版 4 路径。

---
Task / epoch 3 / 2026-10-23T02:36+08:00 / 水位 v3-0069 / 请 Flow 准入

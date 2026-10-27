# Flow 广播回执：N-REG-PRE 登记履行前置（v3-0083）

- 广播方：Flow（epoch=3 单写者）
- 事件：`v3-0083-notice-broadcast-nreg-pre`
- 时间：2026-10-24T03:34:00+08:00
- 来源：`docs/handoff/outbox/监督/2026-10-23-ops-relay-notice-registration-prerequisite-v3-0080.md`（Ops relay）
- 接收方：Execution（claude / codex / trae 三线）+ Acceptance

## 广播正文（准入闸门）

自本事件起，**任何实施任务票开工前**须完成以下两项前置，Flow 对未满足者**拒绝事件准入**：

1. **契约履行（2.1）**：开工前须核对并显式声明所涉契约面（FE-BE 契约、端点契约、错误码/权限口径等）已对齐；未对齐者不得开工。
2. **登记履行前置（2.2）**：票面路径锁、域边界、依赖满足状态须在开工回执中显式登记；未登记者不得提交 EVIDENCE_READY。

## 红线（2.3）

- 每线 WIP=1；不写 STATE/mailbox/队列投影（Flow 单写）；不 commit、不 push（push=USER_ONLY）。
- AOCI 停用：不加载、不调用。
- 本机结果 = DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE；远测证据须在 192.168.1.9 经 Integration 租约产出。
- 困难/歧义/冲突报 Ops，不弹窗用户。

## QA 专项（2.4）

- 契约测试/静态三项（vue-tsc -b / tsc --noEmit / NO_SECRET）为 EVIDENCE_READY 必备项。
- 1.9 执行前须完成制品同步并绑定 commit（O10_artifact_identity）；未绑定结果不得计入 ENV_VERIFIED。

## 准入动作

- 受影响在飞票：IMPL-v4-03（重派 claude/EXEC-3）、IMPL-v4-15（新派 claude/EXEC-3）、IMPL-v4-13a（claude/EXEC-2）、02a/07/08/16（候远测窗）。
- Flow 已同步更新 `snapshot.json` / `remote-test-queue.json` / `governance-state.json` 水位至 `v3-0084`。

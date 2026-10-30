# INC4-FE-7 trial 试运行八能力（Trae 线交付证据）

- 线别/票号：Trae 线 / INC4-FE-7（增量4 · 权威设计 v3 §4.4）
- 交付时间：2026-10-21（Asia/Shanghai）
- 派令链：s260 派令（INC4 拆票，验收锚+通用边界沿 s251）→ s269 库存全派（队列定义）→ s301 队列维持确认（Trae：9-03/04/05+17.4-01/02→FE-6/7→L5-02/03→7J-41）
- 票面锚：WBS L198（4.5 试运行接线：trial 域端点 FE 承接；八能力 UI 承接=草稿/单节点/指定节点/变量覆盖/依赖模拟/DryRun/SQL 预检/转正式，WF-15~22 语义沿大盘盘点 §48+归档 WBS 工作流域 L59-64）；票面估 2 端点，实锚后端契约真源 `datara-backend/rebuild/trial/api.py` 现役 7 端点全量映射（超集承接）；验收锚沿 s260（L200 验收门 5 执行状态部分 trial 八能力+L205 退出标准 3 同 FE-6/s308 口径——Playwright 八能力逐项归 1.9 侧 E2E 票，本票交付 FE 面契约+UI 承接+契约测试）

## 一、交付面

1. `datara-newweb/src/services/rebuild/trialApi.ts`（432 行）：trial 域 FE 面契约 7 方法——createTrialSnapshot/getTrialSnapshot（快照创建+读取）/runTrial（携 snapshot_id 执行）/promoteTrialRun（携 snapshot_id 转正式）/createTrialRun（runs 记录）/getTrialRunOutput（输出面）/promoteRunById（按 runId 转正式）；类型面 `TrialSnapshotStatus='ACTIVE'|'STALE'`/`TrialRunStatus='SUCCEEDED'|'FAILED'|'DRY_RUN'`/`TrialTaskStatus='SUCCEEDED'|'FAILED'|'SKIPPED'`/`TrialDependencyMockStatus='SUCCEEDED'|'FAILED'` 导出；逐方法映射后端契约真源 `datara-backend/rebuild/trial/api.py`（Base path `/api/v1/rebuild/trial`，挂载点 rebuild/api/app.py include_router，TRIAL_BASE='/rebuild/trial'）。
2. `datara-newweb/src/stores/trialRun.ts`（185 行）：试运行状态承接（snapshot/runResult/output/promote 结果+options.testVariables/dependencyMock）。
3. `datara-newweb/src/components/TrialRunPanel.vue`（381 行）：试运行八能力 UI 承接面板（草稿/单节点/指定节点/变量覆盖/依赖模拟/DryRun/SQL 预检/转正式入口；parseObject 泛型化校验 JSON 对象入参）。
4. 契约测试 3 件：`trialApi.contract.test.ts`（306 行，7 方法逐项映射断言）/ `trialRun.contract.test.ts`（385 行）/ `trialRunPanel.contract.test.ts`（276 行）。
5. `CONTRACT_REGISTRY.md` 登记：§1 行 17（trialApi GREEN 7/13）+ 状态快照（GREEN 15/RED 2；冻结方法合计 127）+ §3 FE-7 回归行 + §4 trialApi 冻结行。

## 二、三绿门实测（机器实跑串行）

1. `vue-tsc -b`：零错（修复 1 处 TS2322：parseObject 泛型化 `<T extends Record<string, unknown>>`+dependencyMock 调用处显式 `parseObject<Record<string, TrialDependencyMockStatus>>` 后 EXIT=0）。
2. `npx vitest run` 全量：**515 passed / 0 failed（47 测试文件）**（470 基线递增 +45，零退化；其中本票三件贡献 +38：trialApi 契约 13/trialRun store 12/TrialRunPanel 13；其余 +7 为同窗并行线新增件贡献，不在本票报验面）。
3. `npm run build`：通过（863ms）。

## 三、票面文件 Manifest（s280② 三件套之一；SHA256 全量 64 位小写实测）

| # | 路径 | SHA256 | 行数 |
|---|------|--------|------|
| F1 | datara-newweb/src/services/rebuild/trialApi.ts | 08dc0d21735f69967ee34218c40594d8cbef891be04eb41c7b5880a6c81e77c3 | 432 |
| F2 | datara-newweb/src/services/rebuild/__tests__/trialApi.contract.test.ts | bc22d03be4aa0bf5be79f7ea0a9d3000f0a6ff3300e926650cae1b50c5dcf9df | 306 |
| F3 | datara-newweb/src/stores/trialRun.ts | c8e934a68ffc9328580e48ceaab42c6e658d7207e173ac7ec2995449d8704df2 | 185 |
| F4 | datara-newweb/src/stores/__tests__/trialRun.contract.test.ts | 450de7307e94116aec93bddaf836319f1b4be8f6b61431b26195cc7e217e468d | 385 |
| F5 | datara-newweb/src/components/TrialRunPanel.vue | ac792ef6b69a470373f84ae926e2f8b8bbf0d4a2ea5876f242f0117d237004f9 | 381 |
| F6 | datara-newweb/src/components/__tests__/trialRunPanel.contract.test.ts | 6d5480f2096e65b7378c8028a0b8306cc8683dcab47a2fd45a383e0ce6b1e7b2 | 276 |
| F7 | datara-newweb/src/services/rebuild/CONTRACT_REGISTRY.md | 738e3d214df0e9c1a64bab9d222c8d92312d74b3da03b9bc2527dee0c7a64a92 | 118 |

## 四、共享登记面共存与并行件归属

1. 全量递增归属：vitest 515/47 中本票三件贡献 +38（trialApi 13/trialRun 12/panel 13），其余 +7 归同窗并行线新增件（资源管理视图契约等），零触碰零引用入本票报验面。
2. CONTRACT_REGISTRY.md 跨线共存：头部「最近更新」行与状态快照行为共享行（本票更新后 GREEN 15/RED 2；冻结方法合计 127）；本票登记=§1 行 17+§3 FE-7 回归行+§4 trialApi 冻结行，行级完好，属共享登记面正常共存非冲突非覆盖。
3. FE-6 证据 Manifest F3（CONTRACT_REGISTRY.md）记 `1fbca0c9…` 系落笔笔误澄清：FE-6 收口态实测 SHA=`1832cd3b82940cb69e73e147000ba98311a725c9cad89209302967919704e008`（115 行），与 s307 验收登记的 L18-05 终态值一致，文件从未漂移；FE-6 已随 s308 验收收口，特此历史澄清，不需返工。

## 五、基线与纪律

- FE-7 开工基线 commit：`6a2f327e09463ae84c218b8bbb3246392a87938d`（监督线笔34：FE-6+Codex 四组验收收口；本票 6 代码件工作区未提交 ??×6+registry M×1，候监督线代提交，沿 s280②）。
- 全量基线零破坏：vitest 515/47 = 470 基线（FE-6 验收态 s308）递增 +45，既有 42 件零退化。
- metricsApi/memberApi/projectMenu 七段/router 路由基线零触碰；`.git` 只读零 push；零 `aoci_*`（#85）；设计稿期1/2/3 冻结不动；后端 M 态件与并行线件零触碰；R-45 口径沿 s305 更正（仅脱敏）。
- 测试范式沿 S252；panel 测试铁律本票实证沿用（store 桩为普通对象非 reactive：渲染断言先置状态再 mount 或重挂 fresh panel，事件→调用类断言不受响应性影响）；s280② 三件套=文件清单+逐件 SHA256+基线 commit（本证据件随 tr-done-28 body manifest 第 8 件报验）。

## 六、下一单申报

INC4 队列顺位自转：9-03/9-04/9-05+17.4-01/17.4-02 按队列候摘取；试运行面板挂接 WorkflowGraphWorkbench 侧栏补丁票候 FE-7 验收后评估（FE-6 画布已 s308 验收，挂接前置条件满足）。

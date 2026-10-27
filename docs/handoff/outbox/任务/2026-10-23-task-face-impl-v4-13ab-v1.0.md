# IMPL-v4-13 拆分票面 **13a / 13b**（v1.0，质量五项批 B）

- **发起**：Task / epoch 3 / 2026-10-23T02:37+08:00（实测）/ 基于 v3-0069
- **依据**：Decision 裁定 `DECISION-DEC-v4-D05-ruling`（2026-10-23，Q2=C、Q3=A）+ Ops R4 的 03 目录锁口径
- **拆分理由**：三页组件不触 FE-SHELL（07 锁）与 `e2e/`（03 锁），可立即开工；壳激活/Playwright 须候 07/03 DONE。沿用 02a/02b、16/17 拆分先例。
- **增补事实（Task 只读核验）**：Q3 的 `alertSent` 实存于 metrics 域（`metricsApi.listQualityRuleLinks → QualityRuleResultLink.alertSent`，已 GREEN 接线；后端 `POST /rebuild/metrics/quality-rule-links`），**不在** governance `quality-runs` 载荷（`quality_run_payload` 无该字段）。故告警页消费 metricsApi，**零后端改动**。

---

## IMPL-v4-13a｜质量批 B 组件段（三页，不含壳）

| 字段 | 值 |
|---|---|
| base_priority | P2 |
| effective_priority | P2 |
| priority_basis | WBS 14.4 批 B；D05 已裁（Q2=C 前端聚合先行、Q3=A alertSent 展示）；07 批 A 已交付同域口径；不占 1.9 窗口，是无阻塞可开工项 |
| priority_override | null |

- **依赖**：`DEC-v4-D05`（已裁 2026-10-23；候 Flow 采信入投影）。无其它票面依赖。
- **paths（新文件）**：
  - `datara-newweb/src/views/qc/QualityExceptionView.vue`
  - `datara-newweb/src/views/qc/QualityReportView.vue`
  - `datara-newweb/src/views/qc/QualityAlarmView.vue`
  - `datara-newweb/src/views/__tests__/qualityExceptionView.contract.test.ts`
  - `datara-newweb/src/views/__tests__/qualityReportView.contract.test.ts`
  - `datara-newweb/src/views/__tests__/qualityAlarmView.contract.test.ts`
  - （可选，仅当聚合逻辑抽出）`datara-newweb/src/views/qc/qualityAggregation.ts`
- **禁触**：`governanceApi.ts`、`metricsApi.ts`（只读消费）、`router/routes.ts`、`navigation/menu*.ts`、`e2e/`（13b/03 域）。
- **验收标准**：
  1. 异常核查页：消费既有 `GET quality-runs`（客户端筛 failed/非成功态），`checked_rows=failed_rows+success_rows+skipped_rows` 恒等如实展示；
  2. 报告页（Q2=C）：前端聚合须**明示统计窗口与样本数**；分页取尽（`page_size≤200`，累计到 `total` 或达显式上限 `N`）或显式标注「基于前 N 条」，**禁止静默截断**；**禁止客户端高频轮询**（仅手动刷新/进入时取数）；窗口运行数 >5,000 或触分页上限 → 记录触发日志并报 Ops 立项 A 端点票，**本票不得扩界**；
  3. 告警页（Q3=A）：仅展示/筛选 `alertSent`，页面须明示「告警为状态展示，不含通知投递」，零建模、零投递；
  4. 三件契约测试 GREEN；`vue-tsc -b` 与 `tsc --noEmit -p tsconfig.node.json` EXIT 0；NO_SECRET 0 命中；
  5. 1.9 组件测试经租约（建议 RT-13A，串行窗排 RT-16 后）出具权威证据；本机结果为 `DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`。
- **授权路径**：Task 票面 → Flow 准入派单（建议 claude / EXEC-2 或 EXEC-3 空档线）→ 执行席本地段 → EVIDENCE_READY → RT 租约 → PASS → 集成窗。
- **证据要求**：本地静态三项 + 契约测试输出；远端证据绑定租约/制品 commit/命令/时间戳/退出码/日志/执行者；聚合口径实证（窗口、样本数、是否取尽）留痕。

## IMPL-v4-13b｜质量批 B 壳激活（路由 + 菜单 + Playwright）

| 字段 | 值 |
|---|---|
| base_priority | P2 |
| effective_priority | P2 |
| priority_basis | WBS 14.4 批 B 闭环退出标准；三页唯一壳收口段 |
| priority_override | null |

- **依赖**：`IMPL-v4-13a`（三页组件）+ `IMPL-v4-07` DONE（FE-SHELL 锁释放）+ `IMPL-v4-03` DONE（`e2e/` 锁释放）。
- **paths**：`router/routes.ts`（仅 +3 路由）、`navigation/menu.ts`（仅 qc-exception/qc-report/qc-alarm 三行 future→formal）、`navigation/menuAudit.ts`（仅对应 3 行台账）、`router/__tests__/routes.contract.test.ts`（冻结基线 +3）、`navigation/__tests__/menu.contract.test.ts`（冻结基线同步）、`datara-newweb/e2e/qc-b.spec.ts`（新）。
- **验收标准**：路由/菜单各仅一处改动且增量追加式（不得回退他票在途行）；Playwright 三页「异常核查→报告→告警」闭环截图+JSON 成对；全量 vitest 基线不退化；1.9 e2e GREEN 绑定租约证据。
- **授权路径**：13a PASS 且 07/03 DONE 后转 READY → Flow 派单。
- **证据要求**：同上 + 逐行归因（他票行不计本票）。

---

## 版本记录

- **v1.0（2026-10-23T02:37）**：依 D05 裁定将原 IMPL-v4-13 拆为 13a/13b；四字段、依赖、路径、验收、证据齐备。

---
Task / epoch 3 / 2026-10-23T02:37+08:00 / 水位 v3-0069 / 请 Flow 准入并派 13a

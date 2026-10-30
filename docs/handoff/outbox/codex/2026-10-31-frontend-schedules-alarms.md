# 前端定时与告警接线收口（2026-10-31）

- 任务包：待办 `docs/plans/2026-10-30-consolidation-and-simulation-todo.md` §三 A.3；权威设计 §9.5、§10.5、§10.10 R6/R8；用户 2026-10-31 裁定本次 R6 先验收站内、邮件、Webhook，短信待实施。验收项：定时列表与上下线入口、告警规则及触发记录、工作流变量上下文；前端定向测试与类型检查通过。
- 改动文件：`datara-newweb/src/views/TaskCenterView.vue`、`src/views/__tests__/taskCenterView.contract.test.ts`、`src/views/variables/VariableManagerDrawer.vue`、`src/views/variables/__tests__/variableManagerDrawer.scope.contract.test.ts`、`src/services/rebuild/orchestrationApi.ts`、`src/components/OrchestrationAlarmPanel.vue`、`src/components/WorkflowScheduleList.vue`、`src/components/__tests__/workflowScheduleList.contract.test.ts`；提交 `0347bf8`。
- 验证：`npm test -- src/views/__tests__/taskCenterView.contract.test.ts src/components/__tests__/workflowScheduleList.contract.test.ts src/views/variables/__tests__/variableManagerDrawer.scope.contract.test.ts`，33 passed；`npm exec vue-tsc -- -b --noEmit --pretty false`，退出码 0；`git diff --check`，退出码 0。均为本机逻辑/类型验证。
- 遗留：编排网关定时、告警 API 仍在未提交代码中；1.9 隔离部署与页面 E2E 尚未执行。短信通道按用户裁定列为待实施；告警 `/dep/alarm` 旧设计与本次任务中心项目级配置不一致，后续文档按最新裁定更新。权威 §一的 `datasourceApi.ts` 旧 service 仍挂在已退役画布调用链，须清理。
- 下次第一步：编排网关域把定时与告警 API 代码按独立单元测试并提交；其余代码修正收齐后，在 1.9 依 §10.7 验收。涉及节号：待办 §三 A.3、权威 §9.5/§10.5/§10.7/§10.10。

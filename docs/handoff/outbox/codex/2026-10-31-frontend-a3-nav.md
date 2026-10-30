# 前端 A.3 导航收口（2026-10-31）

- 任务包：待办 `docs/plans/2026-10-30-consolidation-and-simulation-todo.md` §三 A.3；权威 `docs/designs/2026-10-29-dbx-unified-target-design.md` §一、§10.10 R8；目标文件 `datara-newweb/src/components/DepOpsSubNav.vue`、`datara-newweb/src/components/__tests__/depOpsSubNav.contract.test.ts`。验收：部署运维不再显示全局 `/task-group` 快捷入口；项目内任务组承载保持独立。
- 已落地文件：上述两个前端文件；提交 `6edadfb`。
- 验证：`npm test -- src/components/__tests__/depOpsSubNav.contract.test.ts`，3 passed；`git diff --check`，退出码 0。仅为本机逻辑验证，1.9 页面未验收。
- 遗留：`TaskCenterView.vue` 的定时、告警及变量接线仍在未提交工作树；告警 R6 存在后端契约裁定依赖，不宜混入本票。`datasourceApi.ts` 是权威 §一唯一残留旧 service，其消费者挂在已退役 `WorkflowGraphWorkbench`，清理需连同该退役调用链和相关测试处理。
- 下次第一步：前端域先处理退役画布调用链与旧 `datasourceApi.ts` 删除，再核对定时/告警独立可运行单元；涉及节号：待办 §三 A.3、权威 §一、§10.5、§10.10。

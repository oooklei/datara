# 前端 → 编排网关交接（2026-10-30）

- 涉及节号：权威 §10.5、§10.7 C1、§10.10 R8；用户最新要求工作流定时归集、移除部署运维“当前项目任务组”。
- 已落地文件（未提交）：`datara-newweb/src/views/TaskCenterView.vue`、`datara-newweb/src/components/WorkflowScheduleList.vue`、`datara-newweb/src/services/rebuild/orchestrationApi.ts`、`datara-newweb/src/components/DepOpsSubNav.vue`、两个相应定向测试文件。前端 `npm exec vue-tsc -- -b --noEmit` 通过。
- 未完事项：编排网关新增 `/workflow-schedules` 分页列表及 `/{id}/online|offline`，海豚侧节点选项与变量画布桥；前端对 1.9 运行态未验证，定向测试未运行。
- 下次第一步：按海豚 `SchedulerController` `/projects/{projectCode}/schedules` 接网关，带项目权限校验；随后在 1.9 验证定时列表与上下线。

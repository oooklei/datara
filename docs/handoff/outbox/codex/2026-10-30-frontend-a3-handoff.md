# 前端页面域 A3 交接卡（2026-10-30）

- 任务包：待办 `docs/plans/2026-10-30-consolidation-and-simulation-todo.md` §三 A.3；权威 `docs/designs/2026-10-29-dbx-unified-target-design.md` §一、§10.10 R8 与告警桥接。目标文件为 `datara-newweb/src/views/TaskCenterView.vue`、其契约测试、`src/components/DepOpsSubNav.vue`、`src/navigation/projectMenu.ts`、`src/router/index.ts`，以及下述直接引用文件。
- 已落地文件：`datara-newweb/src/views/TaskCenterView.vue`、`datara-newweb/src/views/__tests__/taskCenterView.contract.test.ts`；提交 `c5c798c`。移除模板中心 tab 与空态；旧 `?tab=templates` 回落任务编排。
- 源码核对：`/task-group` 链路已由 `src/navigation/menu.ts` 正式菜单 → `projectMenu.ts` 全局别名集合 → `router/index.ts` 当前项目跳转 → `ProjectSegmentView.vue` 任务组组件承载；未改动。权威 §一所列旧页面/service 中仍存 `src/services/rebuild/datasourceApi.ts`，并被 `NodeConfigPanel.vue`、`ScriptResourceEditor.vue` 引用，不能仅删除文件。
- 验证命令与结果：本机 `npx vue-tsc -b --pretty false` EXIT 0（静态检查）；遵用户最新顺序，运行测试与 1.9 容器验证待全部代码修正、部署后执行，当前不作验收结论。
- 未完事项：A3 其余对标项；旧数据源 service 到 dbx 连接的前后端契约迁移（`ScriptResourceEditor.vue` 仍把 datasource 参数当数字 id）；任务中心告警与 SLA 仍是说明性空态，与权威 §10.10 的 datara 告警桥接目标不一致；1.9 `datara-newweb-web` 仍未更新。跨域后端契约须在对应域修正，再回前端接线。
- 下次第一步：新会话先选定单一域并声明任务包；若继续前端，先核对 dbx 连接 ID 与脚本执行参数契约，再改 `datasourceApi.ts` 的两个消费者。涉及节号：权威 §一、§四、§10.10；待办 §三 A.3。

# 前端权限切换核对交接

- 任务包：权威设计 §五，监控中心权限与项目可见性；目标文件为 `datara-newweb/src/router/index.ts`、`src/router/routes.ts`、`src/views/HomeView.vue`、`src/layouts/AppShell.vue`、`src/services/rebuild/rolePermissions.ts` 及对应契约测试。
- 本票代码改动：无。上述文件多数含并行未提交改动，未代为覆盖或提交。
- 已核对：工作区已有 `/dep/monitor` 的 `monitor:read` 路由守卫、首页入口和部署运维子导航显隐；developer 角色矩阵不含该权限。`rtk npm test -- --run src/router/__tests__/projectGuard.contract.test.ts src/views/__tests__/homeView.contract.test.ts src/layouts/__tests__/appShell.project.contract.test.ts src/services/rebuild/__tests__/rolePermissions.contract.test.ts`：4 文件、44 测试通过。
- 未证实：用户实测的未授权监控可见、切回 admin 后项目不可见是否在部署版本修复。`AppShell.vue` 项目上下文监听路由而未监听账号变化，需结合实际登录流程判断是否构成复现路径；静态测试未覆盖完整账号切换与后端项目响应。
- 下次第一步：在本机 WSL 隔离验证环境按 zhangsan → admin 顺序执行浏览器 E2E，记录 `/session`、`/projects` 与菜单/页面结果；先确认部署版本与当前代码一致，再决定是否补前端或后端缺口。

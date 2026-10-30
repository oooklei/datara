# 前端部署运维导航与 DBX 加载交接（2026-10-31）

- 任务包：待办 §三；权威 §五、§八、§10.10 R9；用户最新裁定“无试运行、上线后走 worker”。
- 已落地 `4592f85`、`d4b0b18`：`datara-newweb/src/components/DepOpsSubNav.vue`、`navigation/menu.ts`、`views/ide/DbxIdeView.vue` 及对应三个契约测试文件。
- 判断：运行时节点不是当前编排运行依赖，已撤掉导航入口；原路由和页面暂仍可直达。海豚资源文件是 worker 依赖文件树，区别于项目脚本开发，菜单改名“运行依赖文件”。
- 后续用户纠正：脚本开发仍支持 Python/Shell 试运行。已在 `45e184e` 恢复部署运维“SSH 试运行节点”入口；上线工作流仍由 DolphinScheduler worker 执行。定向导航测试 20 passed。
- 验证：导航/IDE 定向 Vitest 25 passed；IDE 复测 5 passed；`npx vue-tsc -b --noEmit` 通过。
- 遗留：1.9 浏览器实测；仅旧“运行时节点”路由与后端能力待清理。DBX iframe 内部业务请求失败仍需 DBX 自身错误回显，宿主提供“重载 DBX”。
- 下次第一步：在 1.9 隔离目录部署前端，复测初次加载、会话失败、iframe 加载失败、重载恢复。

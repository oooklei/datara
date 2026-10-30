# 前端账号切换项目列表交接

- 任务包：权威设计 §五身份与项目管理、监控中心入口；目标文件：`datara-newweb/src/views/HomeView.vue`、`src/layouts/AppShell.vue`、`src/views/__tests__/authAccountSwitch.contract.test.ts`。
- 现状核对：监控 `monitor:read` 菜单、首页入口、路由守卫和 developer 拒绝规则均已存在；本票未重做。发现首页仅挂载时取项目、壳仅路由变化时重取项目，账号原地切换有旧列表残留或 admin 不重新加载的竞态。
- 落地：提交 `21e70ba5` 仅补账号变化清空和重取项目、丢弃旧请求响应；新契约测试覆盖 zhangsan → admin 后首页与顶栏列表。`rtk npm test -- --run src/views/__tests__/authAccountSwitch.contract.test.ts` 2/2 通过；`rtk npm run build` 通过。
- 并行提交修复：独立 index 遇 HEAD 并发推进，`21e70ba5` 意外删除 5 个电商仿真文件；已在 `1835fe4` 原样恢复。`git diff --exit-code 21e70ba5^ HEAD -- <五文件>` 退出码 0，HEAD 五个 blob 存在。后续不得再用独立 index 提交。
- 遗留：未在本机 WSL 完成 zhangsan → admin 浏览器 E2E；1.9 已部署版本是否包含当前前端权限规则仍需核查。主站前端其他并行脏改动未代为提交。

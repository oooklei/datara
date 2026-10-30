# SQL IDE 前端会话与路由交接

- 任务包：权威设计 §一、§四、§七 P1；保留原版 DBX SQL IDE，Datara 负责项目会话与 owner 访问入口。
- 已落地：`datara-newweb/src/views/ide/DbxIdeView.vue`、`datara-newweb/src/services/rebuild/dbxIdeApi.ts`、`datara-newweb/src/views/ide/__tests__/dbxIdeSession.contract.test.ts`（`c0754ae`、`3eb0eb3`）；`deploy/wsl-frontend/ide-verify.nginx.conf`（`3a24db8`）。
- 验证：`rtk npm test -- --run src/views/ide/__tests__/dbxIdeSession.contract.test.ts`，3/3 通过；`rtk npm run build` 通过；`rtk git diff --check -- datara-newweb/deploy/nginx.conf` 通过。
- 未完：`datara-newweb/deploy/nginx.conf` 的 `/ide/api/*` owner 网关路由仍为未提交改动。该文件此前已有其他并行改动，不能整文件代为提交。WSL 配置尚未部署和 E2E 验证；1.9 直接 DBX API 端口的访问边界仍需核查。
- 下次第一步：先核对主 Nginx 文件的共享改动归属，再只提交本票路由改动；在本机 WSL 部署，验证 `/ide/` 静态文件正常、无会话 `/ide/api/*` 返回 401、带项目会话访问受 owner 约束、用户/项目切换不泄露旧会话。

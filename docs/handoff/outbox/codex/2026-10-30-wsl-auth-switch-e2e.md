# WSL 账号切换与 IDE 匿名链路验证

- 任务包：权威设计 §四、§五、§10.7 中的 IDE owner、项目可见性和监控权限；验证入口仅本机 WSL `http://localhost:18121`，1.9 只提供后端服务。
- 已落地文件：`deploy/wsl-frontend/verify-auth-switch-wsl.cjs`，用 WSL Playwright Chromium 对现有 `dev`、`admin` 账号执行登录、退出、切换与只读页面检查；验证后退出 admin。未创建或修改业务数据，也未读取 1.9 验证密钥。
- 环境：`18121` 容器挂载当前 `datara-newweb/dist`，页面引用 `index-478gXd4D.js`，构建时间晚于 HomeView/AppShell 账号切换修复；WSL 独立路径装 Node 22 和 Chromium headless。
- 命令：`rtk proxy wsl.exe --exec /root/datara-verify-node/node-v22.15.0-linux-x64/bin/node /mnt/d/需求/数据治理工具/Datara/deploy/wsl-frontend/verify-auth-switch-wsl.cjs`，退出码 0。
- 实测：`/ide/` 和 `/ide/assets/i18n-DvdMpN9C.js` 均 200，匿名 `/ide/api/connection/list` 为 401；`dev` 的监控快捷入口为 0，直达 `/dep/monitor` 被重定向到 `/`；切回 `admin` 后工作台显示 1 个项目、监控入口为 1，监控页面可进入；浏览器令牌未进入 localStorage/sessionStorage，页面异常 0。
- 边界：使用现有 `dev`（developer）验证角色限制，未取得用户实测的 `zhangsan` 凭据，故其个人授权与共享资源行为未验证。DBX 1.9 直连端口的 owner 绕过仍未封闭；本票 E2E 不证明 owner 全链路达标。

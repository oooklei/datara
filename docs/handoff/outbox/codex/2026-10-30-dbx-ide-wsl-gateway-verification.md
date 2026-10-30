# DBX IDE WSL 网关验证交接

- 任务包：权威设计 §四 owner 隔离、§10.7 IDE 相关验收；验证入口为本机 WSL `localhost:18121`，只读检查 1.9 DBX 服务。
- 本票改动：重载 WSL 隔离容器 `datara-ide-verify-20261030` 的 Nginx；未改动 1.9 容器或测试数据。
- 验证结果：`/ide/` 200；此前报错的 `/ide/assets/i18n-DvdMpN9C.js` 200；无会话 `/ide/api/auth/check`、`/ide/api/connection/list`、`/ide/api/query/run` 均 401；无尾斜杠 `/ide/api` 404；无令牌 POST `ide-session` 401。当前 DBX 网关契约测试 31/31 通过。
- **未通过的安全边界**：从 WSL 直接访问 `http://192.168.1.9:4224/ide/api/connection/list` 返回 200，响应为 13 项连接数组；`auth/check` 也为 200。该直连口绕过 Datara owner 网关，故 owner 隔离不能宣称完成。不得把 WSL 代理 401 当作全链路隔离证据。
- 未完：实际 zhangsan → admin 浏览器登录切换、项目列表与监控权限 E2E；主站 Nginx 文件中的 IDE 网关路由尚未独立提交；DBX 直连端口边界需在 DBX/部署域处理。
- 下次第一步：先核对 1.9 DBX 容器的发布端口与 Datara 后端访问路径，设计不影响并行海豚服务的封口方案；然后以 WSL 独立部署复测 13 项连接在无授权直连时不可读，再做用户切换 E2E。

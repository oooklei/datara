# DBX IDE 入口交接（2026-10-30）

- 权威节号：§一第 20 行（SQL IDE → dbx）、§四第 78 行（连接与配置 owner）、§七 P1 第 155 行。
- 本票已落地：`c5f679e` 为隧道目录保存加数据库跨进程锁；`4ea59e1` 登记验证结果。改动文件：`datara-backend/rebuild/dbx/{tunnel_owner.py,ide_proxy.py}`、`datara-backend/tests/rebuild/test_dbx_tunnel_lock.py`、对应 outbox 卡。
- 验证：DBX 六个测试文件 44 passed；SQLite 独立会话锁等待测试通过；Ruff 检查通过；`localhost:18121/ide/` 在未运行重负载编译时 HTTP 200、首字节约 14 ms。
- 入口发现：`datara-newweb/deploy/nginx.conf` 和 `deploy/wsl-frontend/ide-verify.nginx.conf` 目前将 `/ide/` 全部直通 1.9 DBX；`datara-newweb/src/views/ide/DbxIdeView.vue` 第 39 行直接加载 iframe `/ide/`，未调用 `POST /api/v1/rebuild/dbx/projects/{id}/ide-session`。因此现状绕过 Datara owner 网关；单独改 Nginx 会使 iframe API 缺少 `datara_dbx_ide` cookie。
- 未完：前端须先获取短时 IDE 会话、成功后再挂载 iframe，并处理切换用户/项目后的会话重置；Nginx 应把 `/ide/api/*` 重写到 Datara `/api/v1/rebuild/dbx/ide-proxy/*`，静态 `/ide/*` 保持原版 DBX。随后在本机 WSL 验证 admin/owner/共享者/无授权者及动态资源加载。1.9 DBX 直连端口的绕过风险还须在目标部署网络边界处理。
- 下次第一步：新会话选“前端页面”域，以 `DbxIdeView.vue`、相关测试和两份 Nginx 配置为最小任务包；先用 `rg` 定位当前认证 token 取得方式与 iframe 生命周期，再实施会话接线。不要修改海豚路由。

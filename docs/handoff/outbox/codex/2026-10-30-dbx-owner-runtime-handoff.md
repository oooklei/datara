# DBX owner 与本机 WSL 运行交接（2026-10-30）

- 权威节号：§四第 78 行、§七 P1 第 155 行；本票未读取归档区。
- 已提交：AI 配置 owner 网关 `81b9f150`、证据卡 `3c52e32`；提示词模板和个人指令 `81f186b`、证据卡 `afe9d86`；隧道配置 owner 合并 `5bced24`、证据卡 `244d890`。改动文件为 `datara-backend/rebuild/dbx/{ai_owner.py,tunnel_owner.py,api.py,client.py,ide_proxy.py,models.py}`、`datara-backend/rebuild/api/app.py` 的两行建表接线及对应 `test_dbx_*` 测试。共享 `app.py` 其余未提交改动未纳入这些提交。
- 验证：本机 Python 编译通过；DBX 五个单元/契约测试文件 43 passed；新增两个模块 Ruff 全规则通过，修改文件 Ruff `F,E4` 通过。上述证据不等于 WSL E2E。
- 运行状态：本机 WSL `Ubuntu-24.04` 现有 `18121` IDE Nginx 和 `18092` 前端容器已恢复；隐藏常驻 `wsl.exe --exec sleep infinity` 进程曾返回 Windows PID 31908。停止高负载 DBX 编译后，`18121/ide/` 约 17 ms、i18n 资源约 16 ms，均 HTTP 200。`18121` 直接代理 1.9 DBX，不能作为 Datara owner 隔离验收页。
- 未完：带内部 token 的 DBX v0.6.60 二进制构建在 WSL `/root/datara-dbx-auth-build-v06060` 因拖慢页面被主动停止；源码已通过此前 `cargo check`，无可执行文件。Datara WSL 虚拟环境 `/root/datara-backend-dbx-verify-venv` 已安装后端依赖且 `create_app` 导入通过。网关未完成 WSL 部署/E2E；隧道保存仍缺跨进程/DBX 直连并发下的原子更新保障。
- 下次第一步：先确认 `18121`/`18092` 仍快速可用，再设计 DBX 隧道保存的版本/CAS 接口或等效跨进程锁；构建必须低优先级或隔离资源，并在构建期间测页面响应，超阈值即停止。随后在独立 WSL 端口打通 DBX token + Datara 网关，再做 owner/共享/撤销浏览器实测。

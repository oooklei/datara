# DBX 隧道配置 owner 隔离代码票（2026-10-30）

- 权威节号：§四第 78 行、§七 P1 第 155 行。
- 提交：`5bced24`。改动文件：`datara-backend/rebuild/dbx/{tunnel_owner.py,api.py,ide_proxy.py}`、`datara-backend/tests/rebuild/{test_dbx_ide_proxy.py,test_dbx_gateway_api.py}`。
- 已落地：隧道 profile 列表按 owner/共享过滤；共享项凭据和私有路径被遮蔽，测试调用由网关取 DBX 保存的原项；保存时以 DBX 全量清单为基底合并当前 owner 可修改项，保留他人和未认领的旧项；admin 可认领旧 profile，owner 可显式共享。网关进程内使用保存锁。
- 验证：`rtk pytest -q` 指定五个 DBX 测试文件，43 passed；新增 `tunnel_owner.py` Ruff 全规则、修改文件 `ruff --select F,E4` 均通过。
- 未完：DBX 的底层接口仍是整表替换；多 Datara 进程或 DBX 直连并发修改时尚缺跨进程原子更新保障，不能据此声称并发隔离验收通过。本机 WSL 页面 E2E 未完成；DBX 内部 token 二进制构建因拖慢用户页面已停止。
- 下次第一步：补隧道 profile 的跨进程写入保护或 DBX 端原子更新，并在隔离 WSL 入口验证完整保存/共享/撤销链路。

# DBX 隧道目录跨进程写锁代码票（2026-10-30）

- 权威节号：§四第 78 行、§七 P1 第 155 行。
- 提交：`c5f679e`。改动文件：`datara-backend/rebuild/dbx/{tunnel_owner.py,ide_proxy.py}`、`datara-backend/tests/rebuild/test_dbx_tunnel_lock.py`。
- 已落地：隧道整表保存前取得 Datara 数据库锁，再读取 DBX 当前清单、合并当前 owner 的变更并提交。SQLite 使用 `BEGIN IMMEDIATE`，PostgreSQL 使用事务 advisory lock，MySQL/MariaDB 使用命名锁；不支持的数据库显式返回 503。网关进程锁继续保留。
- 验证：`rtk pytest -q` 指定六个 DBX 测试文件，44 passed；SQLite 双会话测试确认第二写入等待第一提交；新增和修改文件 Ruff 检查通过。
- 遗留：PostgreSQL/MySQL 锁尚无对应运行库实测；DBX 直连 session 可绕过 Datara 锁，目标部署须限制直接写入或在 DBX 端加入版本/CAS；本机 WSL E2E 尚未执行。
- 下次第一步：检查目标 IDE/Nginx 路由，确保所有用户写入都走 Datara 网关；随后在独立 WSL 服务验证共享/撤销与并发保存。

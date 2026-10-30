# DBX AI 配置 owner 隔离代码票（2026-10-30）

- 权威节号：§四第 78 行、§七 P1 第 155 行。此前交接卡所写「§五」为定位错误，以本卡为准。
- 提交：`81b9f150`。改动文件：`datara-backend/rebuild/dbx/{ai_owner.py,api.py,client.py,ide_proxy.py,models.py}`、`datara-backend/rebuild/api/app.py`（仅导入与建表两行）、`datara-backend/tests/rebuild/{test_dbx_client.py,test_dbx_gateway_api.py,test_dbx_ide_proxy.py}`。
- 实现：AI 配置逐用户可见；新建与修改校验 owner；批量导入逐项写入，避免 DBX 全局批量接口清空他人配置；admin 可认领旧配置；owner 可显式共享；共享列表隐藏密钥、头、代理和端点；AI 调用由网关取原配置并回填凭据；默认配置和聊天选择按项目/用户保存；流式会话 ID 按用户隔离，Agent 连接按可见连接检查。
- 验证：`rtk pytest -q` 指定五个 DBX 测试文件，39 passed；`python -m py_compile` 指定修改模块通过；新增 `ai_owner.py` 的 Ruff 全规则通过；修改的 DBX 文件 `ruff --select F,E4` 通过。全量 Ruff 在既有文件报大量长行，未作为本票通过证据。
- 未完：本机 WSL 部署及浏览器 E2E 尚未执行；DBX 内部 token 补丁尚未部署，当前运行链路不能据此判定通过。`tunnel-profiles`、`prompt-templates` 等其他 DBX 配置域仍待单独 owner 稽核。共享工作区的 `app.py` 其他未提交改动未纳入本提交。
- 下次第一步：核对 WSL 当前 DBX/Datara 服务与内部 token 是否已部署，再按权威 §10.7 的相关验收项做本机 WSL 实测；随后继续其他配置域。

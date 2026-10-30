# DBX 提示词配置 owner 隔离代码票（2026-10-30）

- 权威节号：§四第 78 行、§七 P1 第 155 行。
- 提交：`81f186b`。改动文件：`datara-backend/rebuild/dbx/{ai_owner.py,api.py,ide_proxy.py}`、`datara-backend/tests/rebuild/{test_dbx_ide_proxy.py,test_dbx_gateway_api.py}`。
- 已落地：提示词模板默认仅 owner 可见和修改，admin 可认领旧模板，owner 可显式共享且共享者只读；个人全局指令按项目/用户存储，避免写入 DBX 的单用户全局值。
- 验证：`rtk pytest -q` 指定五个 DBX 测试文件，41 passed；新增模块 Ruff 全规则、修改文件 `ruff --select F,E4` 均通过。
- 未完：本机 WSL 实际页面验收未完成；隧道配置 `tunnel-profiles/save` 是整表替换接口，仍保持阻断，需设计防跨 owner 覆盖的原子更新；DBX 内部 token 二进制构建因影响页面加载而暂停。
- 下次第一步：继续 §四配置 owner 范围，核对隧道配置的最小原子变更路径；运行验收须先保证 WSL 页面响应不受构建影响。

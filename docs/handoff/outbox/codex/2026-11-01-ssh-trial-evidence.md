# C12 SSH 试运行证据卡

## 本地专项回归

- `python -m pytest -q tests/rebuild/test_r4_resources_edit_api.py tests/rebuild/test_sshnode_api.py`：`14 passed`。
- 覆盖 Python/Shell 试运行的节点可见性、显式共享、`allowTrial` 门禁、语法失败不执行、stdout/退出码回显及凭据不回显。

## 1.9 只读盘点

- admin `GET /api/v1/rebuild/ssh-nodes`：存在 `node-1.9`（id 1）和 `node-bad`（id 2），均 `enabled=true` 但 `allowTrial=false`。
- admin/dev `GET /api/v1/rebuild/ssh-nodes/trial-candidates`：均返回空列表。

## 判定

C12 的代码与契约测试已通过，但 1.9 没有被授权的 SSH 试运行节点，无法在不改变运维配置/不冒险连接 root 主机的前提下执行 SQL/Python/Shell 真实 E2E；因此不宣称真实试运行通过。

## 下一步

需管理员明确授权一个安全的 SSH 节点并将 `allowTrial=true`，再在 1.9 执行三类脚本并记录 stdout/来源/共享边界。

## 涉及节号

收口计划 §三 C12；权威设计 §六、§10.7、§10.8。

# C.7 项目清理跨项目引用防护

- 涉及节号：待办 §三 C.7；实施权威 §四。
- 改动文件：`datara-backend/rebuild/governance/project_cleanup.py`、`datara-backend/rebuild/api/app.py`、`datara-backend/tests/rebuild/test_governance_api.py`。
- 结果：带 `project_id` 的治理行仅按本项目归属删除；若外项目行引用待删治理对象，项目删除返回 409 并回滚。新增跨项目引用回归断言。
- 本机验证：`python -m compileall -q` 对上述三个文件，退出码 0；`git diff --check --` 对上述三个文件，退出码 0。
- 遗留项：全部代码修正完成并更新 192.168.1.9 容器后，运行 `tests/rebuild/test_governance_api.py`；核对真实数据库外键行为与专用命名空间清理零残留。
- 下次第一步：继续编排网关域代码稽核；进入其他域前按交接卡重开会话。

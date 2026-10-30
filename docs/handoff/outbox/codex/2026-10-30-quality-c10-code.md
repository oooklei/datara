# C.10 质量规则行级执行代码交接

- 涉及节号：待办 §三 C.10；实施权威 §四后端“指标与质量”及 §七 P2。
- 已落地文件：`datara-backend/rebuild/governance/api.py`、`datara-backend/tests/rebuild/test_governance_api.py`。
- 判定：绑定可见 dbx 连接的规则已有真实 `checked_rows` / `failed_rows` 统计；无绑定时改为 HTTP 409，不再生成“结构校验 0 行成功”的运行记录。
- 本机验证：`python -m compileall -q datara-backend/rebuild/governance/api.py datara-backend/tests/rebuild/test_governance_api.py`，退出码 0；`git diff --check -- ...`，退出码 0。
- 遗留项：全部代码修正完成后，在 192.168.1.9 部署并运行 `tests/rebuild/test_governance_api.py`、`tests/rebuild/test_quality_dbx.py`；运行证据回填仿真注解映射表。
- 下次第一步：继续同一后端域代码核查，完成剩余代码修正后再进入 1.9 部署与测试。

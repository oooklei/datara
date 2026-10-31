# 编排网关 → 前端交接（2026-10-30）

- 涉及节号：权威 §10.8 M3/M9、§10.9、§10.10 F1–F6；最新用户要求优先闭环节点选项。
- 已落地文件：`datara-backend/rebuild/orchestration/api.py`、`datara-backend/tests/rebuild/test_orchestration_governance_api.py`（未提交，待方案裁定与 1.9 测试）。数据源列表已改为 DBX owner 过滤，并加定向契约测试。
- 发现：海豚 3.4.3 `TaskExecutionContextFactory` 使用 `Map<Integer, AbstractResourceParameters>`，共享字段 `use-datasource.ts` 的选项值也是 number；DBX `connectionId` 是字符串。用户已裁定**坚持节点直接保存 DBX 字符串 ID**。内部 `/internal/dbx/connections/{id}/params` 仍读旧 Datara 数据源，未修。
- 未完事项：按用户裁定改海豚前端共享字段、SQL/PROCEDURE/DATAX/SQOOP 等任务参数与资源容器、master 解析；新增 DBX 安全取参端点；1.9 部署后运行定向测试。不得把当前未提交代码当作已验收。
- 下次第一步：先扩展海豚资源容器的 DATASOURCE 字符串键通道，再改任务插件与 master；保持非数据源资源的整数键兼容。

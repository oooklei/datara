# §10.10 R6 告警桥接契约冲突

- 涉及节号：待办 §三 A.3；权威 §10.10 R6、§9.5。
- 已落地文件：本票未改后端代码；前端现状见 `2026-10-30-frontend-a3-alarm-contract-handoff.md`。
- 核查证据：权威 §10.10 要求沿用 `/dep/alarm` 邮件/短信配置并由编排网关感知海豚失败；当前前端无 `/dep/alarm` 路由，`datara-backend/api/alerts.py` 只有只读列表，`datara-backend/alert/channels.py` 仅支持站内、邮件、Webhook 且短信明确不支持；`rebuild/orchestration/api.py` 没有 DAG 保存参数投影入口。现存 `/rebuild/schedule/alerts` 为自研调度记录，不能当作海豚告警桥接。
- 验证：限定目录 `rg` 定位及对应片段读取；未运行测试或部署。
- 遗留项：按 AGENTS.md 环境冲突规则，告警通道与 `/dep/alarm` 契约待用户刷新；§9.5 需要确定海豚画布保存经何入口回写 datara 变量真源。不得用自研调度告警冒充海豚失败发送。
- 可执行方案：新建 datara 项目级告警策略/触发记录 API 与任务中心页，海豚失败由网关轮询或事件接入；现有站内/邮件/Webhook 可复用，短信需明确供应商接口与配置后接入。
- 下次第一步：取得用户对短信供应商或阶段边界的裁定；随后实现真实桥接并在 1.9 更新后验收。

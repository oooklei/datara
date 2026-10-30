# 工作流 tt 保存错误排查交接（2026-10-31）

- 任务包：权威 §六、§10.4、§10.8；`datara-newweb/src/views/TaskCenterView.vue`、`services/rebuild/dsBridge.ts`、`datara-backend/rebuild/orchestration/api.py`、1.9 海豚 API/元数据库只读核查。
- 已确认：画布 iframe 直接保存到 DolphinScheduler API，datara 编排网关不代理保存；1.9 `tt` 工作流 code `188346193457664`、version 2，两个 SHELL 节点；API 容器含 SHELL 插件，两节点已存 `rawScript` 长度 32/17。
- 上游 3.4.3 `WorkflowDefinitionServiceImpl.generateTaskDefinitionList` 的异常可能折叠成 `REQUEST_PARAMS_NOT_VALID_ERROR`；公开同类报错不构成本次根因证据。
- 改动文件：无；验证命令：1.9 只读 `docker ps`、容器插件目录、PostgreSQL 工作流/任务元信息查询，均成功；未读取运行日志。
- 遗留：缺少本次保存失败的 Network URL、响应 JSON、提交体字段；未复现具体无效字段，未实施修复或 E2E 验收。
- 下次第一步：拿到用户 Network 信息后，按失败 API 路径核对 3.4.3 控制器/校验分支，复现 `tt` 修改保存并修复；若需部署，使用 1.9 隔离工作目录。

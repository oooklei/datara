# Codex R2 / R4-SYNC 项目隔离与恢复语义复核

日期：2026-10-17  
审计基线：canonical `D:\需求\数据治理工具\Datara`，`main` @ `20d30a4`

## 结论

R2 六个变量端点已经进入 canonical main，且 variables router 已由 `app.py` 挂载；#75 所称“BE rebuild 包零 sync/dependency/resources 实现”针对的是 P0-4 的 R4 三域，不应扩展解释为 R2 未实现。当前 R2 `/run-snapshot` 存在明确的项目隔离缺口：接口只验证 token 有效，随后仅以 `instance_id`/`attempt_no` 读取并返回解析值，没有项目权限校验；快照表也没有 `project_id` 可用于授权过滤。该项应作为 R2 安全阻断/未 GREEN 处理，不能把快照数据交给任意有登录态的项目用户。

另发现 `complete` 的 env namespace 暴露面：`service.py:348-360` 将 `os.environ` 全量作为候选变量，返回 `current_value` 并设 `sensitive=False`；空 prefix 会匹配全部环境变量。有效 token 且对任一项目有 `VIEW_ALL` 的调用者可请求空前缀 completion，读取进程环境中的秘密配置。此行为超出“业务变量可按已批准契约明文返回”的范围；须为 env 变量建立显式 allowlist/秘密键排除，并对空前缀结果设边界。不得把 `REBUILD_DB_URL`、`REBUILD_TOKEN_SECRET`、`REBUILD_VALIDATION_KEY` 等部署密钥作为可补全值返回。

R4-SYNC 的恢复凭证则是未实现的契约能力，而不是已发现 token 攻击：rebuild runtime 尚无 `checkpointRef` 或 durable replay 接口。后续实现应先把 checkpoint 与 project/run/attempt/revision/planDigest 绑定，再做项目权限验证；opaque token 仅是定位凭证，不能替代授权。

另有旧版实例详情 API 暴露问题：`GET /instances/{instance_id}` 需 `view_all`，但按 instance ID 直接查询并把 `row.variables` 原样返回，没有 project membership 校验。旧变量快照明确记录 `{value,source,resolved}`，并按现行旧版裁定不脱敏。该风险属于既有旧 API 的授权/数据暴露面，须与 rebuild R2 的新端点分开登记；是否调整旧版明文约定需要安全/产品所有者复核，不在本报告中擅自改写。

## 代码锚点

- `datara-backend/rebuild/api/app.py:42,714-715`：导入并挂载 variables router。
- `datara-backend/rebuild/variables/api.py:213-228`：`/run-snapshot` 仅调用 `principal()` 验证 token；后续直接调用 `read_snapshot(instance_id, attempt_no)` 并返回数据。
- `datara-backend/rebuild/variables/repository.py:132-155`：snapshot 查询按 `instance_id` 和可选 `attempt_no` 筛选，返回 `resolved_value` 等完整字段。
- `datara-backend/rebuild/variables/models.py:58-75`：snapshot 表包含 instance/attempt/变量值等字段，无 project 归属字段。
- `datara-backend/rebuild/variables/service.py:348-360`：环境变量 completion 读取 `os.environ`，将当前值返回并标记 `sensitive=False`。
- `datara-backend/rebuild/api/app.py:77-83`：运行所需的 DB URL、token secret、validation key 从进程环境读取。
- `datara-backend/api/instance.py:38-42,130-153`：旧实例详情按 instance ID 取记录，`view_all` 是唯一接口权限，响应含完整 `row.variables`。
- `datara-backend/master/variables.py:13,123-132,197-214`：旧变量 snapshot 保留值、来源和解析标志，文档明确明文不脱敏。
- `datara-backend/api/wf_definition.py:708-735`：旧 `resume-from` 接口接受 `fromNodeIds`，不能视作 R4 opaque `checkpointRef` 实现。
- canonical main 的 `rg` 检索未发现 rebuild `checkpointRef`、`supports_durable_batch_replay` 实现。

## 处置建议

1. 请 Trae 在当前 P0-4 合约冻结与接线验收中确认 R4-SYNC 的 project/run/attempt/checkpoint 所有权模型；不得沿用只按整数 ID 查询的跨项目读取面。
2. 将 R2 `/run-snapshot` 归入未完成安全修复，先补齐快照项目归属与授权查询契约，再由 owner 实施 schema migration、接口鉴权和跨项目拒绝验收；不以 FE 隐藏入口代替 BE 授权。
3. 为 R2 env completion 建立非秘密 allowlist 并排除敏感部署配置；加上空前缀的结果边界和拒绝验收。
4. 将旧版 `/instances/{instance_id}` 变量明文响应单独交安全/产品 owner 决策；在决策前保留兼容既有用户数据语义，并限制该端点的 project access 规则。
5. 在真实 attempt 写入链、幂等账本、checkpoint 完整性和授权边界落地前，不声明 durable batch replay 已完成或支持。

## 范围与限制

这是 canonical main 的只读源代码复核，不运行测试、不写业务代码，不修改旧版脱敏策略，不把 R4 未实现误报成当前 token 漏洞。现有 `tests/rebuild/test_r2_variables_api.py:173-210` 覆盖了普通 token 可读快照的路径，但未看到跨项目/角色拒绝断言。审计没有调用 AOCI 写入或维护工具。

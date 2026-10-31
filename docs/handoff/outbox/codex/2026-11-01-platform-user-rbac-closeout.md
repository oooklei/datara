# 平台用户管理与 RBAC 收口卡

## 已落地文件

- `datara-backend/rebuild/api/app.py`
  - `/api/v1/rebuild/users/{id}/role` 支持同角色幂等更新；角色变更响应返回 `role_label` 与 `permission_labels`；数据库约束冲突返回可回显的 409/1006，不再裸冒泡为 500。
- `datara-backend/tests/rebuild/test_identity_api.py`
  - 覆盖角色中文释义、权限摘要与重复授权幂等行为。
- `datara-newweb/src/services/rebuild/userApi.ts`
  - 接入角色目录 `/rebuild/users/roles`，归一化用户角色中文释义/权限摘要。
- `datara-newweb/src/views/system/UserManagementView.vue`
  - 用户管理页显示角色中文释义、权限摘要；页面声明平台角色与项目成员角色分层。

## 验证

- `python -m pytest -q tests/rebuild/test_identity_api.py tests/rebuild/test_identity_contract.py tests/rebuild/test_admin_provisioning.py`：`39 passed`（仅既有 Zookeeper/日志线程环境噪音）。
- `npx vitest run src/services/rebuild/__tests__/userApi.contract.test.ts src/views/__tests__/userManagementView.contract.test.ts`：`4 passed`。
- `npm run build`：通过。

## 角色方案

- 平台层每个用户保留一个有效角色：`admin` 管理员、`developer` 开发者、`operator` 运维操作员、`viewer` 观察者。
- 项目层成员角色独立于平台角色，由具备 `manage_user` 的管理员维护；权限按角色矩阵聚合，不支持用户自行修改权限点。
- 页面保留英文编码用于接口/审计，同时展示中文名称与权限中文释义。

## 1.9 回验（重新合并部署后）

- admin 登录 `POST http://192.168.1.9:18091/api/v1/rebuild/login`：`code=0`。
- `GET /api/v1/rebuild/users`：用户 9 为 `zhangsan`，角色 `developer`，中文释义“开发者”，状态“启用”，权限中文摘要非空。
- `PATCH /api/v1/rebuild/users/9/role` 请求 `{"role":"developer"}`：两次连续请求均 HTTP 200、`code=0`、`role_label=开发者`、`permission_labels` 非空、`revoked_tokens=0`；已确认不再出现 HTTP 500。

## 未完事项

- 尚未使用 zhangsan 本人凭据在 1.9 `18091` 完成登录后业务回验；需凭据或管理员在页面重置密码后执行。

## 下次第一步

在 1.9 以 zhangsan 登录，确认开发者权限页面可用；再由 admin 变更为 `viewer` 后确认其旧 token 失效，完成撤权回验。

## 涉及节号

收口计划 §三 B5；权威设计 §六、§10.4、§10.8。

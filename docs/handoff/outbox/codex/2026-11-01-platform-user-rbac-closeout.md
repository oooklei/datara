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

## 未完事项

- 尚未使用 zhangsan 本人凭据在 1.9 `18091` 完成登录后业务回验；需凭据或管理员在页面重置密码后执行。
- 需在 1.9 部署环境对 `PATCH /rebuild/users/9/role` 做一次实际 Network 回验，确认运行镜像已包含本提交。

## 下次第一步

在 1.9 以 admin 登录平台用户管理，打开 Network，给 zhangsan 切换 `developer`，核对 HTTP 200、`role_label=开发者`、`permission_labels` 非空；再重复切回同角色验证幂等 200/`revoked_tokens=0`。

## 涉及节号

收口计划 §三 B5；权威设计 §六、§10.4、§10.8。

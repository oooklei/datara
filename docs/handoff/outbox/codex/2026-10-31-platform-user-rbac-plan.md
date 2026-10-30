# 平台用户管理 RBAC 收口

## 已落地文件

- `datara-backend/rebuild/identity/contracts.py`
  - 四角色中文名称、33 个权限点中文释义。
- `datara-backend/rebuild/api/app.py`
  - 平台用户列表返回 `role_label`、权限中文释义。
  - 新增管理员专用 `/api/v1/rebuild/users/roles` 角色目录接口，返回编码与中文释义。
- `datara-backend/tests/rebuild/test_identity_api.py`
  - 角色更新/最后管理员保护、角色目录中文释义回归测试。
- `datara-newweb/src/services/rebuild/rolePermissions.ts`
  - 前端角色/权限中文标签。
- `datara-newweb/src/views/system/UserManagementView.vue`
  - 创建和变更角色下拉显示“中文（英文编码）”。
- `datara-newweb/src/views/PermissionMatrixView.vue`
  - 矩阵保留英文编码，并通过标题提供中文释义。
- `docs/adr/2026-10-31-platform-rbac-model.md`
  - 固化单平台角色 + 项目角色的最佳实践决策。

提交：`32260953`、`35c631a6`

## 方案裁定

- 平台账号只保留一个全局角色；项目内成员角色独立。当前不采用多平台角色并集，避免撤权和审计歧义。
- 新用户默认观察者（最小权限）。管理员在平台用户页将张三调整为开发者或运维操作员；角色变更会撤销其旧 token，张三需重新登录。
- 管理员不是“角色所有者”；角色模板由平台维护，具备 `manage_user` 的管理员负责授权操作，所有接口以后端矩阵为最终裁决。

## 验证

- `python -m pytest -q datara-backend/tests/rebuild/test_identity_api.py -k "platform_user_role or role_catalog"`：2 passed。
- `npm run test -- --run src/views/__tests__/userManagementView.contract.test.ts src/views/__tests__/permissionMatrixView.contract.test.ts`：9 passed。
- `npx vue-tsc -b --noEmit`：通过。

## 遗留与回验

- 需在 1.9 部署后，以 admin 登录页面，给张三选择“开发者（developer）”或“运维操作员（operator）”，保存后让张三重新登录并验证菜单/API。
- 先前 DolphinScheduler 3.4.3 编译仍在 1.9 下载依赖，尚未取得最终结果；需继续回收编译结果。

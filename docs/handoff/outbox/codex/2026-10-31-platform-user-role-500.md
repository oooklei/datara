# 平台用户角色更新 500 修复

## 已落地

- `datara-backend/rebuild/identity/repository.py`
  - 新增 `update_role`，将 `Role` 枚举持久化为字符串。
  - 新增 `count_enabled_admins_excluding`，实现最后启用管理员保护查询。
- `datara-backend/tests/rebuild/test_identity_api.py`
  - 新增平台用户角色更新成功及最后管理员降级保护回归测试。
- 提交：`e7b049b5 fix: update platform user roles`

## 根因

`/api/v1/rebuild/users/{user_id}/role` 已调用 `UserRepository.update_role` 与 `count_enabled_admins_excluding`，但仓储未实现这两个方法，合法请求进入路由后触发 `AttributeError`，表现为 HTTP 500。

## 验证

- `python -m pytest -q datara-backend/tests/rebuild/test_identity_api.py -k platform_user_role`：1 passed。
- `python -m pytest -q datara-backend/tests/rebuild/test_identity_api.py`：27 passed；仅既有 SQLAlchemy 警告及本机 ZooKeeper 不可解析降级提示。

## 遗留

- 尚未在 1.9 浏览器登录态回测页面操作；需部署包含 `e7b049b5` 的后端后，在系统管理→平台用户管理执行一次角色修改，确认前端不再显示 500。
- 并行 DolphinScheduler 3.4.3 远程编译仍在下载依赖，结果待回收。

## 下次第一步

部署后使用真实管理员 token 调用 `PATCH /api/v1/rebuild/users/9/role`，确认合法角色返回 200；再验证最后管理员降级返回 409/code=1005。

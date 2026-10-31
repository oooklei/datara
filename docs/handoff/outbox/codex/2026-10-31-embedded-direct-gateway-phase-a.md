# 嵌入直连网关迁移阶段 A 回执

## 已落地

- 新增 `GET /api/v1/rebuild/embed/session?project_id=`，统一执行项目权限门禁并返回 DBX/编排子会话入口，不暴露内部令牌。
- DBX IDE 宿主和任务编排宿主均优先调用统一会话契约，旧会话路径保留回退。
- 1.9 后端与前端构建包已更新；前端新包包含 `embed/session`。

## 验证

- 编排网关测试：26 passed。
- 海豚宿主契约测试：31 passed。
- DBX IDE 宿主契约测试：6 passed。
- 1.9 未登录访问统一接口：401。
- 1.9 当前 DBX 直连候选基础镜像 `dbx:datara-gateway-closeout` 回验：`/ide/` 返回 200，匿名 `/ide/api/connection/list` 返回 401，携带 `X-Datara-Internal-Token` 的内部连接列表返回 200；证明容器侧内部通道鉴权已生效。
- 1.9 候选重构构建已切换无 LTO；四组 Git 依赖源码已按 lock revision 预置到候选上下文并改为本地 path。离线编译进一步暴露 builder 未缓存完整 crates.io registry（`axum` 缺失），因此候选镜像仍未生成；正式 DBX 容器未切换。
- 统一会话接口补齐 POST 入口（保留 GET 兼容）；`python -m compileall -q datara-backend/rebuild/orchestration/api.py` 通过。
- POST 统一会话契约测试：`1 passed, 25 deselected`（`test_orchestration_governance_api.py -k embed_session`）。

## 未完成

- nginx 默认业务 API 尚未切换为容器直连；仍需完成服务端令牌注入、容器端令牌验证和旁路 E2E 后再切换。DBX 容器侧鉴权已回验，候选重构构建还需补齐 builder 的 crates.io 离线缓存。

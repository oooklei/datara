# Patch 构建与 tt 回测状态（2026-10-31）

- 用户要求：尽快完成 DolphinScheduler patch 构建、`tt` 保存修复和回测。
- JDK 结论：本机 `temurin-8\jdk8u504-b01` 缺 `jre/lib/rt.jar`，`temurin-24` 缺 `lib/modules`，两套安装均不可用。
- 远端构建：使用 1.9 API 容器内 OpenJDK 8.0.504；精确 3.4.3 源码树应用 patch 的 `git apply --check` 与 `git apply` 均通过。Maven 已启动并进入依赖下载，但 SSH 连接在首次依赖下载阶段被重置，尚未取得 compile 成功/失败结果。
- `tt` 修复：清理任务 code `188346072598016` 的失效资源引用；工作流两个 SHELL 节点 resourceList 均复核为 `[]`。
- 仍需：重新连接 1.9 继续 Maven（依赖已部分缓存），取得首个编译结果；用户登录态下在 1.9 修改 `tt` 后点击保存，完成浏览器回测。

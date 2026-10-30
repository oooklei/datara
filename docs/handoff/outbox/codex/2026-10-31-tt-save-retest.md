# tt 工作流保存复测（2026-10-31）

- 根因：1.9 `tt`（workflow code `188346193457664`，version 2）的 SHELL 任务参数引用失效资源 `/tmp/dolphinscheduler/default/resources/datara-sample.sh`；`t_ds_resources` 无对应记录。SHELL 插件存在，脚本内容非空。
- 修复：仅更新 `t_ds_task_definition` code `188346072598016`，将失效 `resourceList` 清为空数组；未改脚本、工作流关系或其他工作流。
- 复核：`tt` 两个 SHELL 节点的 `resourceList` 均为 `[]`；服务端 API 可达，匿名请求按预期返回 401。
- 限制：未取得登录态，无法在浏览器内点击保存；需用用户会话在 1.9 打开 `tt` 修改后保存确认。
- 另项：DolphinScheduler patch 已应用到精确 3.4.3 源码并通过 `git apply --check`；本机 Java 启动失败（`temurin-24` 路径无效），完整 Maven 构建仍待具备 JDK 的隔离环境。

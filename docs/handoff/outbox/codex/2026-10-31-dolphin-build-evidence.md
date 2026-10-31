# DolphinScheduler 3.4.3 补丁构建证据

## 任务包

- 范围：§六高优先级收口、§10.7 编排回归。
- 验收目标：补丁可构建、可部署，并复测 `tt` 保存。

## 证据

- 宿主机构建命令：`./mvnw -T 1C -DskipTests -Dmaven.javadoc.skip=true -Dcheckstyle.skip=true package`。
- 宿主机构建失败：宿主机仅有 JRE，Maven 报 `No compiler is provided in this environment`，同时缺少 JDK8 `tools.jar`。
- JDK8 容器重试：使用 1.9 现有 `eclipse-temurin:8-jdk`，挂载 `/lei/dolphinscheduler/dolphinscheduler-3.4.3`，并使用 `-Dspotless.check.skip=true`。截至本卡生成时容器仍停在 Maven Enforcer 依赖解析，尚无退出码。
- 目标模块编译复验：`./mvnw -s /root/.m2/settings.xml -T 1C -DskipTests -Dmaven.javadoc.skip=true -Dcheckstyle.skip=true -Dspotless.check.skip=true -pl dolphinscheduler-api,dolphinscheduler-master,dolphinscheduler-worker,dolphinscheduler-task-plugin -am compile`，JDK8 容器退出码 `0`；API、Master、Worker、Task Plugin 的 `target/classes` 已生成，补丁类已出现在 API/Master 编译产物中。
- `tt` 回归脚本已启动，但工作流列表阶段发生 Playwright 导航上下文销毁，未捕获保存请求，不能判定通过。

## 当前结论

- DolphinScheduler 新镜像尚未发布，线上服务未替换；全量 `package` 曾在 Shade 组装阶段长期无日志增长，因此本轮以目标模块 `compile` 通过作为源码编译证据。
- `tt` 保存与 §10.7 十五项验收仍未完成。
- 下一步：继续观察 JDK8 容器终态；若构建失败，登记精确依赖错误并转入可复现的构建环境处理。

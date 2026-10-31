# DBX 直连构建镜像切换记录

- 任务包：嵌入直连迁移 §阶段A，DBX 容器鉴权镜像构建。
- 已完成：1.9 `/lei/apps/dbx` 预取 Linux x86_64 `ziglang` wheel（阿里云镜像，断点续传成功）；Dockerfile 改为本地 wheel 安装；构建目标移除无关 arm64 apt 依赖；Cargo 使用 rsproxy sparse 索引。
- 验证：Docker 构建已进入 apt 工具链层；该层因 Debian 包索引连接长时间重试而中止，尚未生成新 DBX 镜像。
- 下一步：在 1.9 使用可达的 Debian 镜像或预热 apt 包缓存后重新构建；成功后启动隔离候选容器，回验未授权与短 token 路由。
- 遗留：正式 `dbx` 容器尚未替换，nginx 仍保留现有兼容路径。

# DBX AI 配置 owner 隔离交接卡（2026-10-30）

- 本票任务包：权威设计 §五「配置 owner 化」、§七 P1。目标文件：`datara-backend/rebuild/dbx/ide_proxy.py`、`datara-backend/rebuild/dbx/api.py`、对应测试，以及 DBX v0.6.60 的 AI 路由和前端调用点。验收：默认按 owner 隔离、显式共享可用、密钥不泄露、保留原版 AI 调用。
- 已落地文件：本票尚无代码改动；本卡仅记录交接。此前 DBX owner 网关与内部 token 补丁已有独立提交，勿将其视作 AI 配置完成。
- 已核对：DBX v0.6.60 `/ai/configs`、`/ai/config-item`、`/ai/default-config` 当前使用全局配置；桌面端启动时加载配置，流式 AI 请求携带配置。现有 `ide_proxy.py` 阻断多数 `ai/` 路由，仅开放会话相关路由。因此仅放行 AI 路由不能满足 owner 隔离或密钥保护。
- 验证命令与结果：本票未修改代码，未运行测试。此前独立的 DBX 内部 token 补丁通过 3 个 Rust 模块测试及 WSL `cargo check -q -p dbx-web --no-default-features`；这些结果不证明本票完成。
- 未完事项：核对 DBX 配置模型、前端读取和流式请求的最小字段；设计并实现逐用户默认配置和显式共享时的服务端密钥使用；补相应测试；仅在本机 WSL 做部署与 E2E。
- 下次第一步：在同一 DBX 域，先用限定目录的 `rg` 定位配置类型、路由及前端调用行号，再按 offset 读片段；核对工作区共享改动，避免覆盖并行 agent。读取权威设计仅取 §五和 §七 P1。

# R0：远程环境、资产盘点和迁移基线

> 状态：PASS
>
> 启动时间：2026-10-14（Asia/Shanghai）
>
> 权威项目根目录：`D:\需求\数据治理工具\Datara`

## 1. 开始前影响分析

- 上一增量：无；R0 是本次重建的首个增量。
- 受影响设计：总体架构、I18-I23 承接、部署环境、增量门禁、迁移边界。
- 受影响接口：暂不修改；本轮只核查现有 API、鉴权、数据源、调度和运行资源。
- 受影响数据表：现有 I18-I23 资产及运行相关表，仅盘点，不写入、不删除。
- 受影响中间件：`mysql-meta`、`mysql-src`、`mysql-dw`、Redis、Kafka、Zookeeper。
- 受影响测试页面：R0 不新增业务测试页面；远程环境证据页/证据文件作为资源验收凭据。R1 起必须新增独立验证页。
- 是否需要刷新设计：若现有远程拓扑、I18-I23 表结构或鉴权边界与设计冲突，暂停并回写设计、计划和台账；未发现冲突前不改代码。

## 2. 本增量细化步骤

- [x] 步骤 1：本机静态盘点旧 API、模型、迁移、节点执行器、变量、鉴权和 I18-I23 文档/资产。
- [x] 步骤 2：对未来 `rebuild/` 范围执行旧 API 隐式依赖扫描；R0 不创建该目录、不修改旧代码。
- [x] 步骤 3：在 `192.168.1.9` 隔离目录执行 compose 配置、容器、服务日志和依赖资源检查。
- [x] 步骤 4：在 `192.168.1.9` 的 `mysql-meta` 中创建本次重建专用 schema/用户，并验证 `mysql-src`、`mysql-dw` 数据源可用性；不在本机创建替代运行环境。专用 schema/用户和两套验证数据源均已通过远程验证。
- [x] 步骤 5：形成 I18-I23 表级迁移清单，标记 `MIGRATE`、`READ_ONLY_COMPAT` 或 `RETIRE_AFTER_MIGRATION`。
- [x] 步骤 6：将本机检查结果、远程运行证据、迁移清单和未完成项写入项目主目录。
- [x] 步骤 7：完成 R0 验收；最近 30 分钟 API/Master/Worker 未发现既存异常再次出现，R0 达到 PASS，可进入 R1 的开始前影响分析。

## 3. 本次用户要求与命令

- 时间：2026-10-14（Asia/Shanghai）
- 原始要求：启动 R0。
- 执行结果：已完成本机盘点、远程资源检查、browser-use Web 入口核验、隔离测试库/用户供给、源库/数仓验证和 I18-I23 迁移基线；R0 达到 PASS。
- 未实现任务：无 R0 阻塞项；按计划进入 R1 开始前影响分析。

## 4. 证据索引

证据目录：`D:\需求\数据治理工具\Datara\docs\increments\evidence\R0\`

- `local-static-inventory.txt`：本机静态盘点结果。
- `remote-compose-config.txt`：远程 compose 配置检查结果。
- `remote-compose-ps.txt`：远程容器状态。
- `remote-service-logs.txt`：远程 API/Master/Worker/Redis/Kafka 日志摘要。
- `remote-resource-check.txt`：远程数据库、Redis、Kafka 和测试 schema 供给检查。
- `i18-i23-migration-inventory.md`：I18-I23 迁移处置清单。

## 5. 前端牵引与远程闭环

R0 不实现业务功能，不新增正式前端页面；其门禁由远程运行基线证据替代业务页面验证。R1 起恢复“独立测试页面 → API → Backend → 中间件/资源 → 后台日志 → 页面结果”的完整 browser-use 要求。

## 6. 结束结论

- 状态：PASS
- 证据：`docs/increments/evidence/R0/` 下本机、远程 compose、容器、资源、日志、浏览器和迁移清单证据。
- 遗留任务：确认 API 健康检查统一使用 `/api/v1/health`；Web 已完成从 8090 到 18091 的远程容器重建和 browser-use 入口验证；历史异常已与当前运行周期区分记录。
- 下一增量前置条件：R0 已 PASS；进入 R1 前必须完成 R0→R1 影响分析、步骤细化和 R1 独立验证页准备。

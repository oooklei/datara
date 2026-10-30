# 电商仿真导入与清理契约核对

任务包：权威设计 §二、§四、§五；只读核对当前后端路由与模型。此文是**可执行路径审计**，不是已在共享部署导入的证明。用户要求验证后清除临时测试数据，因此只有存在准确清理路径的对象才进入自动临时导入工具。

| 对象 | 当前创建/读取接口 | 当前清理接口 | 本票处理 |
|---|---|---|---|
| 项目变量 | `GET/POST /api/v1/rebuild/variables?project_id=...`，项目作用域以 `scope=project` 保存 | `DELETE /api/v1/rebuild/variables/{name}?project_id=...&scope=project` | 已实现专用前缀和描述标记的幂等导入/清理；默认 dry-run，变更只允许本机 WSL 且需显式目标、项目 ID、内存令牌 |
| DBX 连接/配置 | Datara owner API 支持连接创建、共享、删除；DBX 原始 API 已不应成为用户直连入口 | 连接有 Datara owner 删除 API；配置对象共享与清理仍需逐类核对 | 暂不由仿真工具创建，避免真实密码及并行 DBX 接入状态影响；先用现有授权连接验证 |
| 治理资产、标签、质量规则 | `POST/GET /projects/{id}/{assets,tags,quality-rules}`；资产可绑定 DBX 连接 | 当前治理路由未见匹配的 `DELETE` | **不自动导入临时对象**；若要作为长期仿真基线，先确定身份、去重键、用途和后续治理方式 |
| 标准、指标、质量报告、告警策略 | 当前路由有 `POST/GET` 及部分状态修改 | 当前治理路由未见匹配的 `DELETE` | 不用于可清理临时测试；验证现有项目 33 对象或待补安全清理契约 |
| 隔离项目 | `POST/GET /projects` | `DELETE /projects/{id}` 只显式检查 workflows、datasources、resources 非空，随后删成员/项目 | 不能靠删除项目清理上述治理记录：治理模型对项目 FK 没有 `ON DELETE CASCADE`；可能失败或遗留数据 |

独立工具：`infra/fixtures/business/import_ecommerce_sim_variables.py`。不带动作参数时只输出四个变量的计划，不访问网络；`--apply-variables` 与 `--cleanup-variables` 只处理 `ecom_sim_20261030_` 前缀且描述包含精确 `simulation-fixture:ECOM_SIM_20261030` 标记的记录。已有同名非夹具记录会拒绝覆盖或删除；重复导入是 no-op。令牌只读 `DATARA_SIM_TOKEN` 环境变量，不在命令行参数、URL 或产物中出现。工具未在共享环境运行变更动作。

下一步：在 WSL 隔离部署用只读令牌先确认项目 33 当前变量与治理对象，再按记录的对象清单决定哪些长期基线可保留；临时变量按工具清理，并以重新读取确认消失。治理域若要自动生成临时对象，需先补明确删除/级联清理契约及测试，不能直接写入共享库后寄希望于项目删除。

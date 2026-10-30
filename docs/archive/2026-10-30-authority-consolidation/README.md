# 2026-10-30 权威收敛归档（docs 根部过时设计文档）

用户裁定（2026-10-30）：**所有开发实施工作以 `docs/designs/2026-10-29-dbx-unified-target-design.md` 为唯一权威**；与之不相关的文档视为过时，归档考古。

本目录收纳 docs 根部被该权威取代/失效的设计文档：

| 文件 | 失效原因 |
|---|---|
| 数据开发IDE.md | datara SQL IDE 需求规格 → 由 dbx SQL IDE 承担（权威 §一/§三） |
| 同步编排端点合一实施计划-20260925.md | datara 自研编排已下线 → 方式 A：海豚为 DAG/调度事实源（权威 §六） |
| 同步编排端点合一与设计态分离设计.md | 同上 |
| 组件管理与发布治理设计.md | 「组件声明」约束已废（2026-10-29 裁定）；组件目录 → 海豚任务节点定义（权威 §三） |
| 组件基线化与逐组件发版设计.md | 同上 |
| 组件开发规范.md | 同上 |
| gate-acceptance-matrix.md | 旧 WBS 逐门验收矩阵 → 验收以权威 §10.7（A1-A4/B1-B2/C1-C3/D1-D4/E1-E2）为准 |
| contract-freeze-registry.md | 旧线契约冻结登记簿（FE-13~19 门禁）→ 契约以权威 §三/§五与 `datara-newweb/src/services/rebuild/CONTRACT_REGISTRY.md` 为准 |
| 目录审计-20261012.md | 历史目录审计快照，仅供追溯 |

### 随线归档的 docs 子目录

| 目录 | 失效原因 |
|---|---|
| `组件基线化/`（36 件） | 旧组件基线化线组件规格（assert/condition/dependent/field_map/file_sync…）→ 组件声明线已废，节点定义归海豚任务面板（权威 §10.8） |
| `qa/`（7 件） | 2026-10-26/27 纠偏线核验/收口报告（M3-M5、增量 18、八门冻结令）→ 旧 WBS 门禁线 |
| `superpowers/` | 2026-10-24 target-completion 设计与计划 → 被 dbx 统一目标设计取代 |
| `use-cases/`（etl/general/stream/sync 四域） | 旧 I 线用例与截图；ETL 分类已裁定删除，流处理归 DAG 画布（权威 §五），同步归海豚编排 |

本目录是历史文档归档，不是需求或状态权威。只读不写、不作现行依据。

## 附：随线归档的旧线代码与值守产物

| 条目 | 说明 |
|---|---|
| `datara-l12-e2e/` | 旧 L12 增量线本机 E2E 调试草稿（probe/diag 脚本、dist tgz、node_modules）；E2E 验收现依权威 §10.7 在 1.9 隔离环境执行 |
| `prototype/` | 旧线静态 HTML 原型（index.html + assets） |
| `dev2-duty-loop.md` | epoch 3「DEV-2 开发席值守循环」workflow 草稿（多 agent 派单线，随旧 WBS 线失效） |
| `outbox-DEV2/` | 同线票包（2026-10-23） |
| `scripts-legacy/` | `apply_m_b1/b2_drafts.py` 旧组件基线化线一次性底稿写入器（调已废的 `/components/baseline/*` API） |

以上均无运行时消费者（已核实 datara-newweb/scripts 无引用）；后端 §三 待删模块（rebuild/datasource、sql_ide、ai_*、llm、model、rb/policy|ledger|lineage 等）**不在本目录**——其删除由权威 §七 P4 按实现路径执行，当前仍被运行时装配引用，提前移出会破坏 P1-P3 在飞改造。

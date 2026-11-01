# Datara 文档总入口（现时基线）

更新：2026-11-01（权威刷新：`docs/designs/2026-11-01-datara-current-authority.md` 成为唯一实施权威）

## 1. 权威顺序

发生冲突时，按以下顺序解释和实施：

1. 用户最新明确裁定与 `docs/handoff/STATE.md` 裁定记录；
2. **唯一实施权威 = `docs/designs/2026-11-01-datara-current-authority.md`**（现时全面设计：目标架构、集成机制、前端结构、后端 API 域、部署、数据与变量、身份与权限、开发约束）；
3. 协作行为唯一权威 = `docs/agents/协作规程.md`；
4. 已在 192.168.1.9 形成运行证据、且已进入当前 Git 历史的实现；
5. 需求输入材料：`docs/*.txt`（评审会议纪要、业务流程、前端融合评审等，由用户持续投放）；
6. 其余历史说明、规划与旧线文档 → 一律归档考古（`docs/archive/`、`docs/increments/archive/`、`docs/handoff/archive/`），只读不写、不作现行依据。

`docs/agents/source-truth.md`（源码真源与发版门禁）与 `docs/agents/container-names.md`（容器命名）属第 2 项配套约束，不替代业务设计。

## 2. 现时架构一句话

**dbx 为唯一数据访问层；海豚只取 DAG 画布 + 运行底座；datara 前端为门户外壳与自有域界面，画布经 iframe 同源直连海豚，数据访问经 iframe 同源直连 dbx；datara 后端只承担身份/会话/门卫与自有域 API。编排网关（后端代理海豚 DAG API）已于 2026-11-01 裁定取消。**

三条唯一正确路径见权威设计 §三；集成机制见 §四。

## 3. 文档分类

| 目录 | 效力 |
| --- | --- |
| `docs/designs/` | 现时唯一实施权威（仅 `2026-11-01-datara-current-authority.md`） |
| `docs/agents/` | 协作、源码真源、容器命名、Issue/Triage、领域文档等配套约束 |
| `docs/handoff/` | 运行状态与席位交接（`STATE.md` 为裁定记录；outbox 为过程记录，非权威） |
| `docs/research/` | 需求分析与仿真验证记录（日期快照，非设计权威；其中指向归档设计的链接为历史引用） |
| `docs/evidence/` | 运行/验收证据 |
| `docs/archive/`、`docs/increments/archive/`、`docs/handoff/archive/` | 归档考古，只读 |

## 4. 本轮归档

2026-11-01 将以下过时文档整体移入 `docs/archive/2026-11-01-authority-refresh/`（`docs/designs/`、`docs/adr/`、`docs/plans/` 现已清空，仅保留现时权威设计）：

- 旧设计线：`2026-10-29-dbx-unified-target-design.md`、`2026-10-29-phase-1-dbx-unified-backend-design.md`、`2026-10-29-dbx-ide-integration-design.md`、`2026-10-29-dbx-variable-completion-design.md`、`2026-10-31-frontend-style-drift-governance-plan.md`、`2026-11-01-identity-resource-governance-design.md`
- 旧 ADR：`2026-10-26-D08-workflow-type-mapping.md`、`2026-10-31-platform-rbac-model.md`
- 旧计划/工作日志：`2026-10-29-dbx-ide-*`、`2026-10-30-consolidation-and-simulation-todo.md`、`2026-10-31-*`、`2026-11-01-工作区收口合并方案.md` 等 13 份

归档文件保留用于审计，不再通过物理删除制造追溯断层；本入口负责明确其效力。

## 5. 环境边界

- 本机：代码修改、语法、类型、lint、架构和契约静态检查。
- `192.168.1.9`：单元/集成测试、容器构建、Compose 校验、接口联调与页面运行验证；前端验证入口固定 `http://192.168.1.9:8090/`。
- 生产目录 `/lei/datara` 未经明确部署批准不覆盖；部署/E2E 验收证据必须出自 1.9 隔离工作目录。

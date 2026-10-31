# Datara 文档总入口（当前有效口径）

更新：2026-10-30（权威收敛：dbx 统一目标设计成为唯一权威）

## 1. 权威顺序

发生冲突时，按以下顺序解释和实施：

1. 用户最新明确裁定与 `docs/handoff/STATE.md` 裁定记录；
2. **唯一实施权威 = `docs/designs/2026-10-29-dbx-unified-target-design.md`**（dbx 统一后的系统瘦身与目标设计；含编排融合方式 A、海豚嵌入 §十、验收 §10.7、实现路径 §七 P1-P4）。同日同线子设计：`2026-10-29-phase-1-dbx-unified-backend-design.md`、`2026-10-29-dbx-ide-integration-design.md`、`2026-10-29-dbx-variable-completion-design.md`（冲突时以 unified-target 为准）；
3. 协作行为唯一权威 = `docs/agents/协作规程.md`；
4. 已在 192.168.1.9 形成运行证据、且已进入当前 Git 历史的实现；
5. 需求输入材料：`docs/*.txt`（评审会议纪要、业务流程、前端融合评审等，由用户持续投放）；
6. 其余历史说明、规划与旧线文档 → 一律归档考古（`docs/archive/`、`docs/increments/archive/`、`docs/handoff/archive/`），只读不写、不作现行依据。旧权威序（2026-10-19 v3 真源 / 2026-10-17 验收 v4 / 2026-10-20 WBS）与 docs 根部旧设计已于 2026-10-30 整体归档至 `docs/increments/archive/2026-10-30-authority-consolidation/` 与 `docs/archive/2026-10-30-authority-consolidation/`。

## 2. 当前总目标

按 `2026-10-29-dbx-unified-target-design.md` 推进 dbx 统一：dbx 为唯一数据访问层，海豚为 DAG/调度事实源（方式 A），datara 编排网关为唯一业务入口；实现路径 §七 P1→P4。当前进度：P3 编排与脚本开发落地推进中（编排网关后端、海豚内核内部信任通道、DBX 数据源解析、部署运维资源环境与监控中心代理已落地；海豚 UI 白名单/数据源字段改造、E2E 验收待完成）。

## 3. 演进脉络

- 早期 V3：产品范围草案，仅供追溯（已归档）。
- 纠偏重构线（2026-10-19 ~ 10-28）：v3 需求真源、验收 v4、单线多增量 WBS 与旧前端对标审计，2026-10-30 整体归档（`docs/increments/archive/2026-10-30-authority-consolidation/`）。
- datara 自研编排（同步编排端点合一、组件声明治理）：随 2026-10-29 裁定下线，设计文档归档（`docs/archive/2026-10-30-authority-consolidation/`）。
- 2026-10-29 起：dbx 统一目标设计确立并成为唯一权威；旧前端退役代码归档于 `docs/archive/2026-10-29-dbx-unified-retirement/`。

## 4. 文档取舍

- **继续遵循**：`2026-10-29-dbx-unified-target-design.md` 全部条款、同线子设计、协作规程、STATE.md 心跳。
- **仅作历史证据**：归档区全部内容（旧 v3/v4/WBS、增量证据、组件治理设计、旧 IDE 规格、旧门禁登记簿）。
- **不进入当前方案**：datara 自研编排画布、组件声明/基线化线、datara SQL IDE/数仓建模/血缘/元数据目录/资产地图/LLM/AI 助手（均由 dbx 或海豚承担，见权威 §一/§三）。

归档文件保留用于审计，不再通过物理删除制造新的追溯断层；本入口负责明确其效力。

## 5. 环境边界

- 本机：代码修改、语法、类型、lint、架构和契约静态检查。
- `192.168.1.9`：单元/集成测试、容器构建、Compose 校验、接口联调与页面运行验证；前端验证入口固定 `http://192.168.1.9:8090/`。
- 生产目录 `/lei/datara` 未经明确部署批准不覆盖；部署/E2E 验收证据必须出自 1.9 隔离工作目录。

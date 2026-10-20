# MANIFEST — 2026-10-20 监督线大归档（docs 根 + 取证件批次）

## 范围与原因
- 2026-10-20 用户重大要求：与唯一项目目标（`docs/increments/2026-10-19-纠偏重构前端权威设计.md`）不相关的前期设计/计划文档归档。
- 本目录收纳原 `docs/` 根 10 件：DAG 旧规范/计划/任务清单 7 件、版本菜单功能映射（html+md）2 件、版本规划与工作量评估方案 1 件、2026-10-13 功能实测报告 1 件（实移 10 件）。
- 同日用户追加裁定（第 11–13 件）：`Datara需求规格说明书_V3.0.docx` + 用户手册（docx + md）**已过时，归档/作废**——不再作为客户需求真源与交互参考；现行唯一需求真源 = `docs/increments/2026-10-19-纠偏重构前端权威设计.md`（本目录实收 13 件）。

## 批次二：取证件物理归档（同日 D3，用户裁定「与目标不相关的项归档」，实收 18 件）

- `i12_proofs/`（12 件）← 原 `docs/increments/i12_proofs/`：I12 验证摘要、G1/G5、complete/closeout/handoff/cat_stream 等 JSON 取证与 board_cat 侧边栏 DOM/PNG 实测证据。I12 增量验证已收口，证据转入考古区，不再作为活跃工作面。
- `datara-backend-docs/increments/`（6 件）← 原 `datara-backend/docs/increments/`：i12_proofs 取证 4 件 + `D12-同步取证收口.md` + `I11-同步任务取证交接单.md`。后端子仓 docs 取证整体并入本归档，`datara-backend/docs/` 目录已撤除。
- 两个空源目录（`docs/increments/i12_proofs/`、`datara-backend/docs/`）已删除；AOCI Scope Change 同步收缩 exclude（`docs/archive/**`、`docs/handoff/archive/**`、`docs/increments/archive/**`、`docs/increments/evidence/**`），i12_proofs 与 datara-backend/docs 场 Entry 由 orphan removal 自动清退。

## 批次三：D4 清理移档（同日，用户已批 D1 甄别清单，实收 3 件）

- `SEED_WF_HANDOFF.md` ← 原 `datara-backend/tools/`：工作流种子交接单，任务已收口，转考古区。
- `2026-10-13-功能实测包.xls`、`.xlsx` ← 原主仓根：早期功能实测附件，随本批清理移入归档（已入库）。
- 同批 D4 清退（未入本目录）：A 组 138 件一次性脚本/验证页物理删除（Git 历史承担归档）；B2 两件 → `docs/increments/archive/2026-10-20/`；ui 截图 3 件 → `docs/increments/evidence/`；`datara-web/deploy/nginx.conf`+`Dockerfile` 移至 `datara-web/` 根保留。

## 保留件（docs 根未归档）
- `README.md`（注：其中旧口径条目待随 WBS 开发计划落地一并刷新）
- `contract-freeze-registry.md` —— G 组门禁 FE-13~19 逐门消费的契约冻结登记簿（活跃验收基础设施）
- `gate-acceptance-matrix.md` —— 逐门验收矩阵模板（活跃验收基础设施）
- `docs/agents/`（过程管理规范）、`docs/handoff/`（活跃心跳）、`docs/adr/`、`GLOSSARY.md`

## 恢复方式
- 批次一（docs 根 13 件）：`Move-Item <本目录文件> docs/<原名>`；文件名未改动。
- 批次二（取证件 18 件）：`Move-Item <本目录子目录>/<文件> <原路径>`——`i12_proofs/<文件>` → `docs/increments/i12_proofs/<文件>`（需先重建目标目录）；`datara-backend-docs/increments/<文件>` → `datara-backend/docs/increments/<文件>`（需先重建目标目录）；文件名未改动。
- 批次三（D4 移档 3 件）：`SEED_WF_HANDOFF.md` → `datara-backend/tools/`；实测包 ×2 → 主仓根；文件名未改动。

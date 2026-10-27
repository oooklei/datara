---
design_type: execution-plan
created_at: 2026-10-28
---

# Datara 前端构建执行计划（单执行线 · WSL Docker 部署 · 1.9 后端联调）

票号：F-UX-EXEC-PLAN-01
日期：2026-10-28
设计真源：[2026-10-28-前端开发构建方案.md](2026-10-28-前端开发构建方案.md)（v2，唯一需求真源）
执行模式：**单执行线**（用户裁定 2026-10-28：排除多 agent 执行计划）——主执行线顺序推进批次，不派生子智能体、不分线并行。

## 0. 环境拓扑（用户裁定 2026-10-28，覆盖方案 D10 的部署面）

```
浏览器 ──> 本机 WSL Docker（前端）
            Ubuntu-24.04 · Docker 29.9.2 · Compose v5.6.1（已核实）
            nginx 容器：serve datara-newweb/dist + 反代 /api
            本机入口 http://localhost:18092（容器 80）
                  │ /api 反代（含 SSE 直通：proxy_buffering off）
                  ▼
            192.168.1.9:18090（远程后端，唯一数据真源，不改代码）
```

- 前端**只在本机 WSL Docker 部署**；`192.168.1.9:18091` 不再承担过程部署，仅保留作既有部署参照。
- 后端**零代码改动**：连接 1.9 既有 rebuild 服务；能力不足项按下文 §1 矩阵与 §3 裁决记录处置。
- 本机开发环（vite dev:18092 开发态 / docker:18092 部署态）与 1.9 的分工：代码、单测、类型、逻辑稽核、构建、部署、E2E 全在本机；后端数据与业务服务全在 1.9。

## 1. 1.9 后端支撑矩阵（本地 rebuild 源码逐项核对 + 1.9 活体探测，2026-10-28）

| 能力 | 结论 | 证据锚 |
|---|---|---|
| HttpOnly 会话（D6/G03） | **已支撑，后端零改动**：`datara_session` cookie（httponly + samesite）与 `token` header 双通道，登录设置/登出清除 | `rebuild/api/app.py` L452-466、L828-832、L1027 |
| SQL IDE 全链路（S1–S8） | **已支撑**：22 条路由齐——metadata 六级（databases/schemas/relations/columns/routines/indexes）+ 对象搜索/定义/lint/执行/**cancel**/**SSE events**/status/结果分页/history CRUD/scripts CRUD/exports（结果导出+表导出+下载+取消） | `rebuild/sql_ide/routes.py` L66-91 |
| S6 高危防护 | **已支撑**：DDL 稽核策略内建（DROP/TRUNCATE/ALTER 分级、drop_column 硬阻断 block 级 findings） | `rebuild/sql_ide/ddl_policy.py` L11、L207-213 |
| S9 数据源粒度鉴权 | 部分支撑：项目级 authorize 齐（含隐藏 404 语义）；数据源粒度端点无 → 按方案风险 7：**前端预过滤 + 展开时既有端点 403 兜底**，不阻塞 | `sql_ide/routes.py` L100-107 |
| 组件执行器（T8） | **支撑 19 个**：NORMAL（sql/python/shell/**dependent**）+ SYNC 7 编排组件 + STREAM 4（+运行态 sync/file_sync）；组件目录为冻结设计面 | `rebuild/component_spec/catalogue.py` L13-27 |
| Palette 其余 15 组件 | **后端无目录无执行器**：逻辑控制 10（start/end/conditions/switch/fork/join/merge/delay/loop/reroute）、数据计算 5（ssh/procedure/http/file/assert）、variable/notify/smoke/demo_pipeline | 同上（缺失面） |
| 工作台聚合端点（D7） | **缺失**（1.9 活体 404 证实）：`/api/v1/rebuild/projects/{pid}/workbench-summary` 不存在 | 活体探测 2026-10-28 |
| G01 SQL 终态 | 后端已支撑（cancel+SSE+status 齐全），缺口仅在前端接线 | routes.py L77-79 |
| LLM（D11） | LongCat-2.0 已连通（1.9 实测既有结论） | — |

## 2. 裁决记录

1. **组件类（用户裁定 2026-10-28）**：新后端暂不能支撑的组件，**不阻塞开发**——P1 Palette 集成范围 = 支撑面内 19 组件全量（含 dependent）；无支撑组件按 G09 口径**不进 Palette、不留死按钮**，待后端目录扩充立项后随批补齐。海豚对标（D15）仅对支撑面内可增强项做记录，不产生阻塞票。
2. **workbench-summary（待裁决，不阻塞）**：默认按方案 D7 **前端 fan-out 降级先行**（并发≤4、可取消、部分失败容忍），不等待后端新增端点；如需聚合端点，另行立项后端批次由用户批准后实施。B2 工作台批次按此默认执行。

## 3. 批次计划（B0–B6，单线顺序，每批含验证与证据门禁）

通用验证纪律：每批先跑目标 vitest，票尾一次全量 `vitest run` + `vue-tsc --noEmit`；部署批次另加 `docker compose build` + 容器冒烟（首页 200 + 经容器代理登录 API 成功）；证据落 `docs/evidence/exec-plan/<批次>/`。

### B0 部署基线（WSL Docker 前端跑通）
1. WSL 内建部署工程 `deploy/wsl-frontend/`：`Dockerfile`（nginx:stable-alpine + dist 拷贝）、`nginx.conf`（SPA fallback + `/api` 反代 192.168.1.9:18090 + SSE 直通：`proxy_buffering off`、`proxy_read_timeout 300s`）、`compose.yaml`（端口 18092:80，restart unless-stopped）。
2. `datara-newweb` 生产构建进容器；`http://localhost:18092/` 打开登录页。
3. 冒烟门禁：容器内登录 admin 走通（cookie 建立）→ 项目选择 → 任一 19 项页面真实数据渲染。
4. 证据：构建日志 + 冒烟截图 + `docker compose ps`。

### B1 P0 基线修复（映射方案 §5 P0）
1. 会话恢复前端接线（G03）：登录后 cookie 会话、刷新恢复原 URL（后端已支撑，纯前端）；保留硬契约（header `token`、15s 超时、1xxx 踢登录）。
2. KPI 下钻契约（G02/D8）：统一 `tab/status/runId/workflowType` 写参/读参。
3. 数据前置（G04/G05/G06）：通过 1.9 后端**既有幂等初始化通道**执行电商项目改名与演示 seed（成员/数据源/资源/变量/版本/定时/治理样例）；不改后端代码，仅数据操作；若既有通道无法完成某项，记入待裁决清单后继续。
4. G01 前端终态接线：SSE 心跳 + 超时回落 + 取消按钮接 cancel 端点。
5. 门禁：四账号登录→刷新→深链恢复；`SELECT 1 AS ok` UI 10 秒内返回。

### B2 任务中心闭环（映射 §5 P1）
1. T1 宿主/内核分层、T2 configure-first 闸门、T3 拖边即引用核对、T4 Inspector 六区块+四 Tab（Codex INSPECTOR-4TAB 已有基础，续作）、T5 保存闸门+2005、T6 运行监控三通道、T7 变量七级链分域、T9 弹窗逐个对齐（13 弹窗按审计 02）。
2. **T8 Palette（按 §2 裁决 1）**：集成支撑面内 19 组件（sql/python/shell/dependent + sync 7 + stream 4 + 运行态 2 说明）及各自配置弹窗；无执行器组件不渲染。
3. overlay 栈 + useDraggable（G08/G10）、死按钮清理（G09）、页签深链 + KeepAlive 三护栏（§7.1.3/4）。
4. 工作台批次并入本批收口：KPI 双带 + 三图（ECharts npm）+ 最近运行，数据走 fan-out 降级（§2 裁决 2 默认路径）。

### B3 样例闭环（映射 §5 P2，全在支撑面内）
同步 7 组件表单端到端（保存/校验/运行）；SQL/Python/Shell/依赖四组件真实执行回写计数；流处理整行选中（G12）+ UI 生产数据→聚合/融合→观摩面板实时结果。

### B4 SQL IDE 完整化（映射 §5 P3）
S1–S8 能力面（CodeMirror 6 内核不变 + 补全/lint/分色/hover、多 Tab、多语句结果、vxe 网格、树懒加载+悬浮菜单 11 项、变量六点联动、历史+导出）；**S9 树根节点化**（删除选择器、根节点=有权限数据源、点击根节点切换执行上下文、展开 403 兜底提示）；S6 前端展示 ddl_policy block 级反馈；去票据文案（G11）；快捷键三件套。验收=与 18093 `#/ide` 并屏对照差异清零（S9 为有意差异）。

### B5 全页面与 UX 收口（映射 §5 P4）
19 项+全局页按钮响应矩阵；数据源三步向导严格复刻；D13 列表搜索逐页铺排（强制）；G14 视觉融合（§2.2 基准）；1440/1024/375 三档；四角色可见性回归。

### B6 统一验收（本机容器 + 1.9 后端）
关键 E2E 一次：四账号、默认电商项目、核心工作流运行、SQL IDE、流融合、LongCat 调用、三档响应式、控制台零未处理错误；对照 §6 验收矩阵逐行取证；候选镜像固化（docker image tag + 导出归档）可回滚。

## 4. 依赖与风险

1. 1.9 后端可用性是全部批次的外部依赖：每批开工前一次健康探测（login + sql-ide 路由 401/404 语义），异常即停线汇报，不重试硬闯。
2. 数据前置（B1.3）依赖 1.9 既有幂等初始化通道的覆盖面；缺口项不阻塞，记入待裁决清单继续后续批次。
3. fan-out 工作台在聚合端点上线前为正式实现（非临时 hack），接口层预留 `workbench-summary` 切换点。
4. WSL Docker 与 Windows 文件系统的构建性能：构建全部在 WSL 内执行（代码经 `/mnt/d` 挂载或构建上下文拷贝），避免跨文件系统 IO 惩罚。

## 5. 热点契约

```
intent: 单执行线按 B0–B6 顺序将 v2 方案落成端到端真实可用前端，部署于本机 WSL Docker、联调 1.9 后端
constraints: 后端零代码改动；无支撑组件不进 Palette 不阻塞；workbench-summary 默认 fan-out 降级；每批证据门禁；SSE 反代直通
success_criteria: 方案 §6 验收矩阵逐行证据通过；容器冒烟与关键 E2E 绿
risk_level: medium
approval_gates: [B0 部署跑通后、B6 验收前]
rollback: 候选 docker 镜像回滚
ownership: 主执行线（Trae 本线）顺序执行，用户裁定收口
```

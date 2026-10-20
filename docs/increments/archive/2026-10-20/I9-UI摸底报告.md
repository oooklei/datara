# I9 · UI 摸底报告（UI 重启前置基线）

> 日期：2026-09-19。
> 背景：按用户裁定，**I9 先完成功能收尾**（mock 主动提示 + 前端配合后端接真 + 回归发布），**UI/交互改造整体后置**——待 I9 执行完毕后，按 design-critic 迭代程序重新启动。本报告是重启时的基线证据，摸底范围：`datara-web/src` 全部视图（68 个文件）+ 图工作台 + 服务层对接状态。
> 配套文档：I9-设计文档.md（F56 工作包/N1~N17 全表）、I9-方案-信息架构与任务中心重构.md（DS 对比归因 + 裁定 1A/2A/3B/4A）、决策记录.md §十六。

---

## 1. 全景数字

| 维度 | 数字 | 说明 |
|---|---|---|
| 路由 | 47 条 | routes.ts：登录 1 + 原有 8 + 模块 37 + redirect 2 + 兜底 1 |
| 视图文件 | 68 个 / 约 1.85 万行 | 最大 QcExceptionView 703 行，>500 行的 11 个 |
| 纯 mock 页面 | ≈42 个 | 直接 `import … from 'services/mock/dataStore'`，共 77 处 mock 引用（≈50 文件） |
| 真实通道页面 | 14 个 | datasourceApi、syncApi、lineageApi、ideApi、graphApi/streamApi 出口 |
| 服务层就绪度 | 6 个 real 模块全部可用 | graphApi / streamApi / syncApi / datasourceApi / lineageApi / ideApi；**多个已发布 API 未被视图接入**（见 §2 加粗项） |
| 双态机制 | 已具备 | services/index.ts `apiMode`（VITE_API_MODE，默认 real）+ `isMock` 导出，视图可做 real/mock 双态 |

## 2. 页面 × 对接状态清单（按侧栏菜单组）

图例：✅ real 已接 ｜ ⛅ mock ｜ ◐ 混合（isMock 双态）｜ ❗ 摸底新增发现

### 总览
| 页面 | 状态 | 证据与问题 |
|---|---|---|
| 工作台 `/` | ❗**硬编码假数据** | DashboardView L3-13：四张统计卡数字 `'3' / '26' / '92.3%' / '2'` 全是字面量——既不是 mock 也不是 API，属最易误导用户的「假真数据」；入口卡带内部话术「Phase 1」（L30）、「U4 · topo profile」（L12） |
| DAG 编排 / ETL 设计 / 流设计包装页 | ◐ | EtlDesignView L12 graphService、StreamDesignView L12 graphService（37 行薄壳，画布内核复用） |

### 数据集成
| 页面 | 状态 | 证据 |
|---|---|---|
| 数据源管理 `/ds/list` `/ds/detail/:id` | ✅ real | datasourceApi（DataSourceListView L11-14，测试/删除/向导全接）；dsUtils 仅取色辅助 |
| 同步任务 `/sync/list` `/sync/detail/:id` | ✅ real | syncApi（I6 F34 接真，SyncListView L10、SyncDetailView L11） |
| 任务中心 `/dag` | ◐ 混合 | wf 页签 real（graphService，TaskCenterView L13）；**runs 页签仍挂 DagRunsView 纯 mock**（L23/L141，F56d 对象）；**候选池 sync/etl/stream 走 listSeedTaskDocs，real 分支也在用 seed**（L14-15，F56d 对象） |
| ETL 任务 `/etl/list` | ⛅ | dataStore+ST（EtlListView L12） |
| 流处理 `/stream/list` `/stream/detail/:id` | ⛅ | dataStore（StreamListView L12、StreamDetailView L12-13）；**streamApi（listStreamJobs/日志/启停/数据预览，I8 已发布）未接入**（F56d 对象） |

### 数据开发
| 页面 | 状态 | 证据 |
|---|---|---|
| 数据开发 IDE `/ide` | ✅ real | datasourceApi L19 + ideApi L23（库表树/补全/执行） |
| 数仓建模 `/model/list·design·lineage` | ⛅/◐ | ModelListView L11 ⛅、ModelDesignView L11 ⛅、ModelLineageView lineageApi L17 ◐ |
| 脚本任务 `/script/*`（Hub 三页签） | ⛅ | ScriptListView L12、ScriptEnvView L10、ScriptRemoteView L12 |
| 参数配置 `/param/*`（Hub 四页签） | ⛅ | ParamGlobalView L11 等 |

### 数据治理
| 页面 | 状态 | 证据 |
|---|---|---|
| 数据质量 `/qc/*` 六页 | ⛅ | QcScoreView L11、QcRuleView L11、QcTaskView L11、QcExceptionView L14、QcReportHubView、QcAlarmView L11 |
| 元数据目录 `/meta/catalog`、标签 `/meta/tag` | ⛅ | MetaCatalogView L11、MetaTagView L10 |
| 血缘分析 `/meta/lineage` | ✅/◐ | lineageApi（LineageView L16-17，isMock 双态） |
| 资产地图 `/meta/map` | ⛅ | AssetMapView L15 |
| 数据标准 `/std/*` 五页 | ⛅ | StdElementView L13 等 |
| 指标管理 `/ind/*` 三页 | ⛅ | IndListView L13 等 |
| 数据安全 `/sec/*` 三页 | ⛅ | SecPermView L10 等 |
| 开放接口 `/open/*` 三页 | ⛅ | OpenApiView L11 等 |

### 部署运维
| 页面 | 状态 | 证据 |
|---|---|---|
| 运行时节点 `/dep/runtime` | ✅ real | graphApi listRuntimeNodes/listSshNodes（DeployRuntimeView L12-15） |
| 部署中心/集群监控/组件日志/告警/运维 `/dep/*` | ⛅ | DeployCenterView L12、DeployMonitorView L11、DeployLogView L12、DeployAlarmView L15、DeployOpsView L10 |

### 双轨/遗留
| 项 | 说明 |
|---|---|
| `/dag/runs` DagRunsView | 506 行纯 mock 运行实例页；引用点 3 处：routes.ts L36、TaskCenterView L23/L141；另 App.vue L45 消息跳转映射 `1: '/dag/runs'`、DagListView L106-110 mock 提示话术「查看 /dag/runs」。与 `/dag/instances` InstanceRunsView（531 行 real）双轨并存 |
| `/deploy` | 已 redirect `/dep/monitor` ✅ |
| PlaceholderView | 兜底「建设中」页，现无路由命中（兜底除外） |

## 3. 图工作台能力矩阵（DAG 画布基线）

### 已有 ✅
| 能力 | 证据（GraphWorkbench.vue 除注明外） |
|---|---|
| 连线建立（拖端口 @connect，自连/重边/成环三重校验） | L229-259 |
| 节点增删改、拖拽移动、落点即存 | L261-292、L304-329 |
| 复制节点（右键） | L387-399 |
| 自动布局（dagre） | L148-153 |
| 校验 / 试运行 / 版本保存（弹备注）/ real 运行对话框 | L123-167 |
| 组件箱：关键字搜索 + 分组折叠 + 拖拽 + 灰置 phase | Palette L9-39 |
| 右键菜单：节点（属性/复制/删除）、画布（自动布局） | L371-405 |
| 浮窗层：日志 / AI / 版本 / 视角注入浮窗 | L195-207 + FloatLayer |
| MiniMap / Controls / Background 已挂载 | L475-477 |
| 只读视角降级（权限 M15 + view 模式周期刷新） | L46、L209-225 |

### 缺失 ❌ / 残缺 ⚠️（→ I9-设计文档 N1~N17 对应）
| 缺口 | 状态 | 证据 |
|---|---|---|
| 连线删除显式入口 | ❌ | 仅 VueFlow 隐式 edges-change remove（L274-282）；无右键菜单、无 hover 删除钮 |
| 连线可供性 | ⚠️ | 端口 hover 无提示、边 hover 无加粗/高亮反馈 |
| 键盘删除 | ❌ | `deleteKeyCode` 未配置（节点选中后 Del 无效） |
| 撤销 / 重做 | ❌ | stores/graph.ts L5-42 仅 doc/dirty/saving，无历史栈 |
| 多选 / 框选 / 成组解组 | ❌ | 无 selectionKeyCode / 框选 / group 机制 |
| 左右面板收放 | ❌ | Palette（L443）、Inspector（L491）直挂，无折叠 rail |
| 查找 / 定位 / 大纲 / 按类型过滤 / 节点显隐 | ❌ | 无任何机制（多流程大画布无法定位目标） |
| 拖入悬停视觉反馈 | ❌ | wb-canvas 仅 `@dragover.prevent`（L448），无 drag-over 态 |
| 网格吸附 / 对齐辅助 | ❌ | 无 snapToGrid / align |
| MiniMap 语义 | ⚠️ | `node-color` 未配置，节点全灰一团（critic 第 1 轮误判为骨架屏） |
| Inspector 空态 | ⚠️ | emoji ☝（Inspector L716-719） |
| 工具栏层级 | ⚠️ | edit 模式 8 键（保存/校验/自动布局/试运行/extraFloats/日志/AI/版本）同级同权无分组（L418-427） |

**用户点名映射**：a 连线与删线 → N1 组（可供性+删除入口）；b 面板收放 → N2/N3；c 组合/过滤/查找/特写 → N4~N7。N1~N17 全表见 I9-设计文档.md §F56b。

## 4. UI 债清单（重启时逐项销账）

1. **话术泄漏**（对用户可见的内部/演示用语）：
   - 「Beta」徽章 — App.vue L144
   - 「Phase 1 · 图内核标杆视角」 — App.vue L176、DashboardView L2/L30
   - 「U4 · topo profile」 — DashboardView L12
   - 副标题「DAG 工作台 · 设计与执行一体化（对齐 DolphinScheduler 工作流定义）」 — DagDesignView L141
   - mock 提示直书内部路径「查看 /dag/runs」 — DagListView L106-110
2. **首页假数据**：DashboardView L3-13 硬编码统计（❗摸底新增发现，误导性高于普通 mock；建议随 F56e 演示标识一并表态，或归 UI 阶段 U0 接真——**待用户裁定**）
3. **emoji 字符图标体系**：侧栏菜单（◆⛁⑃▤⌨⌘⚑✓☰⌇✦⛨⇋⛅）、组件箱 schema.icon、首页统计卡（⑃▶✓!）——需统一图标语言（建议 SVG 线性图标 + 语义色收敛，替代彩虹色 p-ico）
4. **双轨运行实例页**：DagRunsView（mock）vs InstanceRunsView（real）并存，导航口径未收口
5. **画布细节残缺**：MiniMap 全灰、Inspector 空态 emoji、工具栏无层级
6. **菜单结构混杂**：五组 24 项 + 子菜单 30+（DS 六归因对比与三层 IA 方案见 I9-方案文档；裁定 1A/2A/3B/4A）
7. **超长单文件**：QcExceptionView 703 / ScriptListView 657 / ModelListView 643 / ScriptRemoteView 636 / IndListView 573——单页多职责，重启时评估拆分与页签化
8. **mock 全景**：77 处 import / ≈50 文件；已双态收口样板：WfVarPanel、Inspector（isMock 分支）；F56d 切真对象以 I9-设计文档 §F56d 清单为准

## 5. critic 迭代程序备忘（重启时严格照此执行）

> 用户两次下发的原文程序，重启时逐字遵循：

1. Capture a screenshot of the current design
2. Invoke the critic in a fresh context, with just the screenshot, not the code, implementation details, or earlier iterations/critiques
3. Ask it to evaluate the aesthetic that the design is going for, imagine how a top design studio would execute this aesthetic, then outline the biggest gaps
4. Lastly, it should provide a score out of 10 indicating how close the current design is to that studio-level quality bar

Critic prompt 准则：高层结构与细节并重；警惕并惩罚过度/明显的 AI 生成模式；反馈紧凑具体、拒绝空话；大胆有主见、不取安全解。每轮使用**同一份** critic prompt；critic 全新上下文只看截图。循环直到 critic 独立评分达标（达标线不写入 critic prompt）。子代理模型以用户当轮指定为准（前两轮指定 GLM-5V-Turbo、Qwen3-VL Max）。

已留存的复用资产：
- 截图脚本 `C:\Users\Administrator\AppData\Local\Temp\gstack_i9_shot.js`（playwright API 登录 + localStorage 注入 + /#/dag 1600×900 截图）
- 基线截图 `docs/increments/screenshots/i9_baseline_workbench.png`（第 1 轮 critic 评 4/10，8 条差距已录入 §4/§3）

## 6. 重启执行顺序建议（I9 完成后）

| 阶段 | 内容 | 验证门 |
|---|---|---|
| U0 全局地基 | 设计令牌统一、图标语言替换 emoji、话术清理（§4.1 全部）、首页假数据处置 | 构建通过 + 全站无泄漏扫描 |
| U1 DAG 工作台 | N1~N17（连线可供性/删线/面板收放/查找/过滤/显隐/组合/键盘/吸附/MiniMap…） | 画布操作清单逐项演示 |
| U2 IA 收敛 | 按 1A/2A/3B/4A 重组菜单 + 演示分组折叠标识 | 菜单目标态对照 |
| U3 critic 循环 | 截图 → critic 评分 → 差距实现 → 复评，直至 critic 独立评分达标 | critic 分数 |
| U4 回归发布 | 构建 → 部署 1.9 → 全站截图 → 回归单 | 同 I4 模式 |

---

**结论**：真实通道骨架已立（数据源/同步/IDE/血缘/运行时节点/运行实例引擎页 6 类 14 页 real），其余 ≈42 页为 mock 演示态且无主动标识（F56e 待做）；DAG 画布功能内核完整但交互可供性全面缺失（11 项缺口）；话术泄漏 5 处 + 首页硬编码假数据 1 处为用户可感知的最高优先债。I9 功能收尾（F56d mock 接真、F56e 主动提示）完成后，按 §5 程序重启 UI 工作。

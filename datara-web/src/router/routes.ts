import type { RouteRecordRaw } from 'vue-router'
import PlaceholderView from '../views/PlaceholderView.vue'

// 路由表（纯数据，供 index.ts 装配与测试断言；不触 window/location）
// meta.demo=true 表示本期范围外演示模块（F56e：App.vue 顶栏挂「演示数据」标识，提示数据为演示样例）
export const routes: RouteRecordRaw[] = [
  // ---- 登录（F5，免守卫） ----
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { title: '登录' } },

  // ---- 现有 10 条路由（保持不变） ----
  { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '工作台' } },
  { path: '/dag', name: 'task-center', component: () => import('../views/TaskCenterView.vue'), meta: { title: '任务中心' } },
  { path: '/dag/design/:id', name: 'dag-design', component: () => import('../views/DagDesignView.vue'), meta: { title: '可视化编排' } },
  // 集群拓扑独立页（/deploy）已合并入集群监控（DeployMonitorView 内嵌同一 GraphWorkbench 拓扑工作台），老链接重定向
  { path: '/deploy', name: 'deploy', redirect: '/dep/monitor', meta: { title: '集群拓扑' } },
  // /etl/design/:id 已删除（I1 意见③：ETL 设计器入口移除，EtlMappingPanel 删除；页面文件 I9 收尾清理）
  { path: '/stream/design/:id', name: 'stream-design', component: () => import('../views/StreamDesignView.vue'), meta: { title: '流设计器' } },
  { path: '/model/er', name: 'model-er', component: () => import('../views/ErCanvasView.vue'), meta: { title: 'ER画布', demo: true } },
  { path: '/meta/lineage', name: 'meta-lineage', component: () => import('../views/LineageView.vue'), meta: { title: '血缘分析' } },
  { path: '/meta/map', name: 'meta-map', component: () => import('../views/AssetMapView.vue'), meta: { title: '资产地图', demo: true } },

  // ---- 新增 45 条模块路由 ----
  // 数据集成
  { path: '/ds/list', name: 'ds-list', component: () => import('../views/datasource/DataSourceListView.vue'), meta: { title: '数据源管理' } },
  { path: '/ds/detail/:id', name: 'ds-detail', component: () => import('../views/datasource/DataSourceDetailView.vue'), meta: { title: '数据源详情' } },
  { path: '/sync/list', name: 'sync-list', component: () => import('../views/sync/SyncListView.vue'), meta: { title: '同步任务' } },
  { path: '/sync/detail/:id', name: 'sync-detail', component: () => import('../views/sync/SyncDetailView.vue'), meta: { title: '同步任务详情' } },
  // /sync/wizard 与 /batch/board 已删除（I6：独立向导/进度看板下线，同步编排模板归 C23，监控走 syncApi 列表/详情）
  // F56a：ETL/流独立列表页为演示态（数据源/同步/任务中心为真实通道），挂 demo 标识
  { path: '/etl/list', name: 'etl-list', component: () => import('../views/etl/EtlListView.vue'), meta: { title: 'ETL任务', demo: true } },
  { path: '/stream/list', name: 'stream-list', component: () => import('../views/stream/StreamListView.vue'), meta: { title: '流数据处理', demo: true } },
  { path: '/stream/detail/:id', name: 'stream-detail', component: () => import('../views/stream/StreamDetailView.vue'), meta: { title: '流任务详情', demo: true } },
  // 数据开发
  { path: '/model/list', name: 'model-list', component: () => import('../views/model/ModelListView.vue'), meta: { title: '数仓建模', demo: true } },
  { path: '/model/design/:id', name: 'model-design', component: () => import('../views/model/ModelDesignView.vue'), meta: { title: '模型设计', demo: true } },
  { path: '/model/lineage/:id', name: 'model-lineage', component: () => import('../views/model/ModelLineageView.vue'), meta: { title: '模型血缘与影响', demo: true } },
  { path: '/ide', name: 'ide', component: () => import('../views/ide/IdeView.vue'), meta: { title: '数据开发IDE' } },
  // 纯 mock 运行实例页已删除（F56d）：真实运行实例统一走 /dag/instances（InstanceRunsView），老链接重定向
  { path: '/dag/runs', redirect: '/dag/instances', meta: { title: '运行实例' } },
  // I3 调度执行引擎：真实运行实例视图（run_mode 筛选 + 实例 DAG 染色 + 日志抽屉）
  { path: '/dag/instances', name: 'dag-instances', component: () => import('../views/dag/InstanceRunsView.vue'), meta: { title: '运行实例（引擎）' } },
  // 跨流依赖（/dag/depend）已删除：依赖配置统一在任务中心 → 工作流 → 编排「依赖」页签（流内视角）
  { path: '/dag/alarm', name: 'dag-alarm', component: () => import('../views/dag/DagAlarmView.vue'), meta: { title: '告警与SLA', demo: true } },
  /* F56a 同壳单入口：脚本 3 页、参数 4 页、质量报告 3 页、数据标准 5 页各保留一个权威路由，
     页内页签改 query.tab 切换；旧路径 redirect 保书签（原 query 原样透传，如细项报告 table 直达） */
  { path: '/script/list', name: 'script-list', component: () => import('../views/script/ScriptHubView.vue'), meta: { title: '脚本任务', demo: true } },
  { path: '/script/env', name: 'script-env', redirect: (to) => ({ path: '/script/list', query: { ...to.query, tab: 'env' } }), meta: { title: '环境与依赖', demo: true } },
  { path: '/script/remote', name: 'script-remote', redirect: (to) => ({ path: '/script/list', query: { ...to.query, tab: 'remote' } }), meta: { title: '远程执行(SSH)', demo: true } },
  { path: '/param/global', name: 'param-global', component: () => import('../views/param/ParamHubView.vue'), meta: { title: '参数配置', demo: true } },
  { path: '/param/builtin', name: 'param-builtin', redirect: (to) => ({ path: '/param/global', query: { ...to.query, tab: 'builtin' } }), meta: { title: '内置时间参数', demo: true } },
  { path: '/param/env', name: 'param-env', redirect: (to) => ({ path: '/param/global', query: { ...to.query, tab: 'env' } }), meta: { title: '环境参数组', demo: true } },
  { path: '/param/tools', name: 'param-tools', redirect: (to) => ({ path: '/param/global', query: { ...to.query, tab: 'tools' } }), meta: { title: '引用检测与预览', demo: true } },
  // 工作流变量已迁入 DAG 工作台「变量」页签（管理与使用分离），独立页面 /param/wfvars 已删除
  // 数据治理
  { path: '/qc/score', name: 'qc-score', component: () => import('../views/qc/QcScoreView.vue'), meta: { title: '评分总览', demo: true } },
  { path: '/qc/rule', name: 'qc-rule', component: () => import('../views/qc/QcRuleView.vue'), meta: { title: '质量规则', demo: true } },
  { path: '/qc/task', name: 'qc-task', component: () => import('../views/qc/QcTaskView.vue'), meta: { title: '检查任务', demo: true } },
  { path: '/qc/exception', name: 'qc-exception', component: () => import('../views/qc/QcExceptionView.vue'), meta: { title: '异常数据核查', demo: true } },
  { path: '/qc/report', name: 'qc-report', component: () => import('../views/qc/QcReportHubView.vue'), meta: { title: '质量报告', demo: true } },
  { path: '/qc/report-dag', name: 'qc-report-dag', redirect: (to) => ({ path: '/qc/report', query: { ...to.query, tab: 'dag' } }), meta: { title: '专项质量报告', demo: true } },
  { path: '/qc/report-table', name: 'qc-report-table', redirect: (to) => ({ path: '/qc/report', query: { ...to.query, tab: 'table' } }), meta: { title: '细项质量报告', demo: true } },
  { path: '/qc/alarm', name: 'qc-alarm', component: () => import('../views/qc/QcAlarmView.vue'), meta: { title: '质量告警', demo: true } },
  /* 开放接口（一级菜单：本系统产出/运行数据的三类 API） */
  { path: '/open/api', name: 'open-api', component: () => import('../views/open/OpenApiView.vue'), meta: { title: 'API管理', demo: true } },
  { path: '/open/key', name: 'open-key', component: () => import('../views/open/OpenKeyView.vue'), meta: { title: 'API-Key管理', demo: true } },
  { path: '/open/log', name: 'open-log', component: () => import('../views/open/OpenLogView.vue'), meta: { title: '调用日志', demo: true } },
  { path: '/meta/catalog', name: 'meta-catalog', component: () => import('../views/meta/MetaCatalogView.vue'), meta: { title: '元数据目录', demo: true } },
  { path: '/meta/tag', name: 'meta-tag', component: () => import('../views/meta/MetaTagView.vue'), meta: { title: '标签管理', demo: true } },
  // F56a：数据标准 5 页同壳为「标准管理」单入口（StdHubView 页签切换），旧路径 redirect 保书签
  { path: '/std/element', name: 'std-element', component: () => import('../views/std/StdHubView.vue'), meta: { title: '标准管理', demo: true } },
  { path: '/std/code', name: 'std-code', redirect: (to) => ({ path: '/std/element', query: { ...to.query, tab: 'code' } }), meta: { title: '代码标准', demo: true } },
  { path: '/std/naming', name: 'std-naming', redirect: (to) => ({ path: '/std/element', query: { ...to.query, tab: 'naming' } }), meta: { title: '命名规范', demo: true } },
  { path: '/std/mapping', name: 'std-mapping', redirect: (to) => ({ path: '/std/element', query: { ...to.query, tab: 'mapping' } }), meta: { title: '标准映射与合规', demo: true } },
  { path: '/std/approval', name: 'std-approval', redirect: (to) => ({ path: '/std/element', query: { ...to.query, tab: 'approval' } }), meta: { title: '标准审批', demo: true } },
  { path: '/ind/list', name: 'ind-list', component: () => import('../views/ind/IndListView.vue'), meta: { title: '指标目录', demo: true } },
  { path: '/sec/perm', name: 'sec-perm', component: () => import('../views/sec/SecPermView.vue'), meta: { title: '权限管理', demo: true } },
  { path: '/sec/mask', name: 'sec-mask', component: () => import('../views/sec/SecMaskView.vue'), meta: { title: '脱敏规则', demo: true } },
  { path: '/sec/audit', name: 'sec-audit', component: () => import('../views/sec/SecAuditView.vue'), meta: { title: '访问审计', demo: true } },
  { path: '/ind/board', name: 'ind-board', component: () => import('../views/ind/IndBoardView.vue'), meta: { title: '指标看板', demo: true } },
  { path: '/ind/consistency', name: 'ind-consistency', component: () => import('../views/ind/IndConsistencyView.vue'), meta: { title: '一致性检查', demo: true } },
  // 部署运维
  { path: '/dep/runtime', name: 'dep-runtime', component: () => import('../views/deploy/DeployRuntimeView.vue'), meta: { title: '运行时节点' } },
  { path: '/dep/center', name: 'dep-center', component: () => import('../views/deploy/DeployCenterView.vue'), meta: { title: '部署中心', demo: true } },
  { path: '/dep/monitor', name: 'dep-monitor', component: () => import('../views/deploy/DeployMonitorView.vue'), meta: { title: '集群监控', demo: true } },
  { path: '/dep/log', name: 'dep-log', component: () => import('../views/deploy/DeployLogView.vue'), meta: { title: '组件日志', demo: true } },
  { path: '/dep/alarm', name: 'dep-alarm', component: () => import('../views/deploy/DeployAlarmView.vue'), meta: { title: '告警管理', demo: true } },
  { path: '/dep/ops', name: 'dep-ops', component: () => import('../views/deploy/DeployOpsView.vue'), meta: { title: '运维操作', demo: true } },

  // 兜底：未注册路径落到占位而非 404 白屏
  { path: '/:pathMatch(.*)*', name: 'not-found', component: PlaceholderView, meta: { title: '建设中' } },
]

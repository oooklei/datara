/**
 * 正式产品路由（s251 派令 L3-03 解锁：/p/:projectId 项目工作区层注册）。
 *
 * 解锁前基线（增量 1 / 票 1.4）：仅 /login 与 / 两条，无 demo/验证页/catch-all。
 * 已解锁注册：
 *  - /dag                 → dag-entry（TaskCenterView 任务中心，s260 派令 INC4-FE-1
 *                           解锁：顶部视角页签框架照抄；菜单 task-center 组
 *                           batch:inc4 + registeredPaths 门控见 menu.ts / filterMenu）
 *  - /dep/ssh             → dep-ssh（S319/S320 裁定的 SSH 节点独立挂载页）
 *  - /dep/runtime         → dep-runtime（17.4 P3 运行节点迁移：RuntimeNodeView
 *                           运行时节点注册清单 + SFTP 目录浏览；History 直链可达，
 *                           菜单可见性候批——BATCH_SWITCHES.inc17 仍 false，见 menu.ts）
 *  - /p/:projectId        → project-workbench（ProjectWorkbenchView 项目工作台页，
 *                           s251 派令 L3-03）
 *  - /p/:projectId/:seg   → project-segment（ProjectSegmentView 功能段占位页，
 *                           seg 与 PROJECT_MENU_SECTIONS 七段对齐；未知 seg 由视图层
 *                           渲染「未知功能段」，不落首页——§7.3 判据保持）
 *
 * 纪律（1.4 冻结决策延续）：History 模式；无 catch-all（:pathMatch 禁用）；
 * 无 /api 前缀路由；每条路由具名 + 绑定组件；项目归属校验守卫归 L3-05（router/index.ts）。
 */
import type { RouteRecordRaw } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import ProjectWorkbenchView from '../views/ProjectWorkbenchView.vue'
import ProjectSegmentView from '../views/ProjectSegmentView.vue'
import TaskCenterView from '../views/TaskCenterView.vue'
import SshNodeManagementView from '../views/SshNodeManagementView.vue'
import RuntimeNodeView from '../views/depops/RuntimeNodeView.vue'
import ApiKeyManagementView from '../views/ApiKeyManagementView.vue'
import ApiManagementView from '../views/ApiManagementView.vue'
import LlmModelManagementView from '../views/LlmModelManagementView.vue'
import DataSourceListView from '../views/datasource/DataSourceListView.vue'
import IdeView from '../views/ide/IdeView.vue'
import MetadataCatalogView from '../views/meta/MetadataCatalogView.vue'
import AssetMapView from '../views/meta/AssetMapView.vue'
import LineageAnalysisView from '../views/meta/LineageAnalysisView.vue'
import TagManagementView from '../views/meta/TagManagementView.vue'
import StandardManagementView from '../views/std/StandardManagementView.vue'
import IndicatorListView from '../views/ind/IndicatorListView.vue'
import IndicatorBoardView from '../views/ind/IndicatorBoardView.vue'
import ConsistencyCheckView from '../views/ind/ConsistencyCheckView.vue'
import PermissionMatrixView from '../views/PermissionMatrixView.vue'
import QualityRuleView from '../views/qc/QualityRuleView.vue'
import QualityTaskView from '../views/qc/QualityTaskView.vue'
import ResourceManagementView from '../views/resources/ResourceManagementView.vue'

export const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: LoginView },
  { path: '/', name: 'home', component: HomeView },
  { path: '/dag', name: 'dag-entry', component: TaskCenterView },
  { path: '/dep/ssh', name: 'dep-ssh', component: SshNodeManagementView },
  // 17.4 P3 运行节点迁移（IMPL-v4-17）：运行时节点注册清单 + SFTP 目录浏览页
  // （History 直链可达；菜单可见性候批——BATCH_SWITCHES.inc17 保持 false）
  { path: '/dep/runtime', name: 'dep-runtime', component: RuntimeNodeView },
  { path: '/open/key', name: 'open-key', component: ApiKeyManagementView },
  { path: '/open/api', name: 'open-api', component: ApiManagementView },
  { path: '/open/llm', name: 'open-llm', component: LlmModelManagementView },
  { path: '/ds/list', name: 'ds-list', component: DataSourceListView },
  { path: '/ide', name: 'sql-ide', component: IdeView },
  { path: '/meta/lineage', name: 'meta-lineage', component: LineageAnalysisView },
  { path: '/meta/map', name: 'meta-map', component: AssetMapView },
  { path: '/meta/catalog', name: 'meta-catalog', component: MetadataCatalogView },
  { path: '/meta/tag', name: 'meta-tag', component: TagManagementView },
  { path: '/std/element', name: 'std-element', component: StandardManagementView },
  { path: '/ind/list', name: 'ind-list', component: IndicatorListView },
  { path: '/ind/board', name: 'ind-board', component: IndicatorBoardView },
  { path: '/ind/consistency', name: 'ind-consistency', component: ConsistencyCheckView },
  { path: '/sec/perm', name: 'sec-perm', component: PermissionMatrixView },
  { path: '/qc/rule', name: 'qc-rule', component: QualityRuleView },
  { path: '/qc/task', name: 'qc-task', component: QualityTaskView },
  { path: '/resources', name: 'resource-mgmt', component: ResourceManagementView },
  {
    path: '/p/:projectId',
    name: 'project-workbench',
    component: ProjectWorkbenchView,
    props: (route) => ({ projectId: Number(route.params.projectId) }),
  },
  {
    path: '/p/:projectId/:seg',
    name: 'project-segment',
    component: ProjectSegmentView,
    props: (route) => ({
      projectId: Number(route.params.projectId),
      seg: String(route.params.seg ?? ''),
    }),
  },
]

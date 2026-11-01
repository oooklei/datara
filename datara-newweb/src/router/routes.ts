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
 *                           seg 与项目侧栏五组 19 项对齐；未知 seg 由视图层
 *                           渲染「未知功能段」，不落首页——§7.3 判据保持）
 *  - /p/:projectId/system → project-system-admin（SystemAdminView 直挂，
 *                           projectId 透传点亮项目成员管理区块；B5-c 补缺：
 *                           redirect 丢 projectId 导致 ProjectMembersView 永不可达）
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
import MonitorView from '../views/depops/MonitorView.vue'
import OrchestrationResourceView from '../views/depops/OrchestrationResourceView.vue'
import ApiKeyManagementView from '../views/ApiKeyManagementView.vue'
import ApiManagementView from '../views/ApiManagementView.vue'
import TagManagementView from '../views/meta/TagManagementView.vue'
import StandardManagementView from '../views/std/StandardManagementView.vue'
import IndicatorListView from '../views/ind/IndicatorListView.vue'
import IndicatorBoardView from '../views/ind/IndicatorBoardView.vue'
import ConsistencyCheckView from '../views/ind/ConsistencyCheckView.vue'
import PermissionMatrixView from '../views/PermissionMatrixView.vue'
import AccessAuditView from '../views/sec/AccessAuditView.vue'
import QualityRuleView from '../views/qc/QualityRuleView.vue'
import QualityTaskView from '../views/qc/QualityTaskView.vue'
import QualityExceptionView from '../views/qc/QualityExceptionView.vue'
import QualityReportView from '../views/qc/QualityReportView.vue'
import QualityAlarmView from '../views/qc/QualityAlarmView.vue'
import ResourceManagementView from '../views/resources/ResourceManagementView.vue'
import DbxIdeView from '../views/ide/DbxIdeView.vue'
import SystemAdminView from '../views/system/SystemAdminView.vue'
import ProjectTaskGroupView from '../views/ProjectTaskGroupView.vue'

export const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: LoginView },
  { path: '/', name: 'home', component: HomeView },
  { path: '/dag', name: 'dag-entry', component: TaskCenterView },
  { path: '/task-group', name: 'task-group', component: ProjectTaskGroupView, props: (route) => ({ projectId: Number(route.query.projectId) || 0 }) },
  { path: '/dep/ssh', name: 'dep-ssh', component: SshNodeManagementView },
  // 17.4 P3 运行节点迁移（IMPL-v4-17）：运行时节点注册清单 + SFTP 目录浏览页
  // （History 直链可达；菜单可见性候批——BATCH_SWITCHES.inc17 保持 false）
  { path: '/dep/runtime', name: 'dep-runtime', component: RuntimeNodeView },
  { path: '/dep/monitor', name: 'dep-monitor', component: MonitorView, meta: { permission: 'monitor:read' } },
  // 现时权威设计 §五：部署运维四类自建资源页，由同一组件按 kind 驱动。
  {
    path: '/dep/worker-group',
    name: 'dep-worker-group',
    component: OrchestrationResourceView,
    props: { kind: 'worker_group' },
  },
  {
    path: '/dep/environment',
    name: 'dep-environment',
    component: OrchestrationResourceView,
    props: { kind: 'environment' },
  },
  {
    path: '/dep/queue',
    name: 'dep-queue',
    component: OrchestrationResourceView,
    props: { kind: 'queue' },
  },
  {
    path: '/dep/cluster',
    name: 'dep-cluster',
    component: OrchestrationResourceView,
    props: { kind: 'cluster' },
  },
  { path: '/open/key', name: 'open-key', component: ApiKeyManagementView },
  { path: '/open/api', name: 'open-api', component: ApiManagementView },
  { path: '/sys', name: 'system-admin', component: SystemAdminView },
  { path: '/proj', redirect: '/' },
  { path: '/meta/tag', name: 'meta-tag', component: TagManagementView },
  { path: '/std/element', name: 'std-element', component: StandardManagementView },
  { path: '/ind/list', name: 'ind-list', component: IndicatorListView },
  { path: '/ind/board', name: 'ind-board', component: IndicatorBoardView },
  { path: '/ind/consistency', name: 'ind-consistency', component: ConsistencyCheckView },
  { path: '/sec/perm', name: 'sec-perm', component: PermissionMatrixView },
  { path: '/sec/audit', name: 'sec-audit', component: AccessAuditView },
  { path: '/qc/rule', name: 'qc-rule', component: QualityRuleView },
  { path: '/qc/task', name: 'qc-task', component: QualityTaskView },
  // E17/E18/E19（冻结表点名视图）：真实实现页（IMPL-v4-08 质量五项批 A/B），
  // B5-c 纠偏——原挂 QualityReadOnlyView 聚合旧页导致三真实视图成孤儿
  { path: '/qc/exception', name: 'qc-exception', component: QualityExceptionView },
  { path: '/qc/report', name: 'qc-report', component: QualityReportView },
  { path: '/qc/alarm', name: 'qc-alarm', component: QualityAlarmView },
  { path: '/resources', name: 'resource-mgmt', component: ResourceManagementView },
  { path: '/ide', name: 'dbx-sql-ide', component: DbxIdeView },
  {
    path: '/p/:projectId',
    name: 'project-workbench',
    component: ProjectWorkbenchView,
    props: (route) => ({ projectId: Number(route.params.projectId) }),
  },
  {
    path: '/p/:projectId/dep',
    redirect: '/dep/monitor',
  },
  {
    path: '/p/:projectId/system',
    name: 'project-system-admin',
    component: SystemAdminView,
    props: (route) => ({ projectId: Number(route.params.projectId) }),
  },
  {
    path: '/p/:projectId/ide',
    name: 'project-dbx-sql-ide',
    component: DbxIdeView,
    props: (route) => ({ projectId: Number(route.params.projectId) }),
  },
  {
    path: '/p/:projectId/:pathMatch(.*)*',
    name: 'project-segment',
    component: ProjectSegmentView,
    props: (route) => ({
      projectId: Number(route.params.projectId),
      segmentPath: Array.isArray(route.params.pathMatch)
        ? route.params.pathMatch.join('/')
        : String(route.params.pathMatch ?? ''),
    }),
  },
]

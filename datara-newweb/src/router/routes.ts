/**
 * 正式产品路由（s251 派令 L3-03 解锁：/p/:projectId 项目工作区层注册）。
 *
 * 解锁前基线（增量 1 / 票 1.4）：仅 /login 与 / 两条，无 demo/验证页/catch-all。
 * 已解锁注册：
 *  - /dag                 → dag-entry（TaskCenterView 任务中心，s260 派令 INC4-FE-1
 *                           解锁：顶部视角页签框架照抄；菜单 task-center 组
 *                           batch:inc4 + registeredPaths 门控见 menu.ts / filterMenu）
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

export const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: LoginView },
  { path: '/', name: 'home', component: HomeView },
  { path: '/dag', name: 'dag-entry', component: TaskCenterView },
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

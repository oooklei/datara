import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '../services/http'
import { listProjects } from '../services/rebuild/projectApi'
import { authAccount, currentSession } from '../services/rebuild/authApi'
import { roleHasPermission, type Permission } from '../services/rebuild/rolePermissions'
import { PROJECT_SCOPED_ALIASES, rememberActiveProject, selectActiveProject } from '../navigation/projectMenu'
import { routes } from './routes'

const router = createRouter({ history:createWebHistory(), routes })

/**
 * L3-05 上下文守护（s251）：URL 上下文 = 授权上下文，防串项目（权威设计 §3.3 L573）。
 * 守卫语义映射（4041/4042 归属判定；前端唯一可判定源=listProjects 可见集合，
 * 后端无 GET /projects/{id} 单查端点、ownOrJoined 未交付，前端不假设）：
 *  - 4041（项目不存在/不可见）：projectId 非整数 或 不在 listProjects 可见集合 → 拦截回 /；
 *  - 4042（项目作用域子资源 not found）：后端语义，前端由 ProjectSegmentView 占位承载
 *    未知 seg（L3-03 已落地），守卫不拦 seg；
 *  - 403/1003（无归属权操作）：后端九域授权闸门语义，前端不预判（显隐不替代鉴权）。
 * 「项目作用域 API 自动注入 project_id」前端形态：Route props 数字化注入链
 * （URL→props→API 契约显式 projectId 参数，metricsApi/memberApi 既有形态），
 * 守卫保证 URL projectId 归属合法，页面内 API 一律消费 URL 注入的 projectId。
 * 纪律：认证守卫保持先行（增量 1 基线零变化）；归属校验失败 fail-closed 拦截回 /
 * （守护正确性优先于可达性）。
 */
async function hasAuthenticatedSession(): Promise<boolean> {
  if (getToken() || authAccount.value) return true
  try {
    await currentSession()
    return true
  } catch {
    return false
  }
}

router.beforeEach(async (to) => {
  if (to.path === '/login') {
    return getToken() || authAccount.value ? { path:'/' } : true
  }
  const authenticated = await hasAuthenticatedSession()
  if (!authenticated) return { path:'/login', query: { redirect: to.fullPath } }
  const requiredPermission = to.meta.permission as Permission | undefined
  if (requiredPermission && !authAccount.value && getToken()) {
    try { await currentSession() } catch { return { path: '/login', query: { redirect: to.fullPath } } }
  }
  if (requiredPermission && (!authAccount.value || !roleHasPermission(authAccount.value.role, requiredPermission))) {
    return { path: '/' }
  }
  if (PROJECT_SCOPED_ALIASES.has(to.path)) {
    try {
      const page = await listProjects()
      const activeId = selectActiveProject(page.list)
      return activeId === null
        ? { path: '/' }
        : { path: `/p/${activeId}${to.path}`, query: to.query, hash: to.hash }
    } catch {
      return { path: '/' }
    }
  }
  if (!to.path.startsWith('/p/')) return true
  const raw = to.params.projectId
  const id = Number(Array.isArray(raw) ? raw[0] : raw)
  if (!Number.isInteger(id)) return { path:'/' }
  try {
    const page = await listProjects()
    if (!page.list.some((p) => p.id === id)) return { path:'/' }
    rememberActiveProject(id)
    return true
  } catch {
    return { path:'/' }
  }
})

export default router

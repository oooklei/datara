import { createRouter, createWebHashHistory } from 'vue-router'
import { routes } from './routes'
import { getToken, TOKEN_KEY } from '../services/http'
import { apiMode } from '../services'

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

/**
 * F5 登录守卫：非 /login 且无 token → /login（hash 路由）。
 * mock 模式不拦截（纯前端本地测试默认 admin 视角，不挡本地测试）。
 */
router.beforeEach((to) => {
  if (apiMode === 'mock') return true
  if (to.path === '/login') {
    // 已登录访问登录页 → 回首页
    if (getToken()) return { path: '/' }
    return true
  }
  if (!getToken()) return { path: '/login' }
  return true
})

export { TOKEN_KEY }
export default router

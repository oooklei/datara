import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '../services/http'
import { routes } from './routes'

const router = createRouter({ history:createWebHistory(), routes })
router.beforeEach((to) => {
  if (to.path === '/login') return getToken() ? { path:'/' } : true
  return getToken() ? true : { path:'/login' }
})
export default router

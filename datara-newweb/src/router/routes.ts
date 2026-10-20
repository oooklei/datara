import type { RouteRecordRaw } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'

export const routes: RouteRecordRaw[] = [
  { path:'/login', name:'login', component:LoginView },
  { path:'/', name:'home', component:HomeView },
]

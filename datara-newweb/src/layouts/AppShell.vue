<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  filterGlobalMounts,
  filterMenuGroups,
  type MenuFilterContext,
  type RenderableMenuGroup,
} from '../navigation/filterMenu'
import {
  PROJECT_MENU_GROUPS,
  PROJECT_MENU_ITEMS,
  projectItemPath,
  rememberActiveProject,
} from '../navigation/projectMenu'
import { loadGroupFolded, toggleGroupFolded } from '../navigation/groupFold'
import { menuGroups } from '../navigation/menu'
import { listProjects, type ProjectSummary } from '../services/rebuild/projectApi'
import { authAccount, currentSession, logout, type AuthRole } from '../services/rebuild/authApi'
import { ROLE_PERMISSIONS } from '../services/rebuild/rolePermissions'
import { getToken } from '../services/http'
import AiAssistantPanel from '../components/AiAssistantPanel.vue'

const props = defineProps<{ filterOverrides?: Partial<MenuFilterContext> }>()
const route = useRoute()
const router = useRouter()

const loggingOut = ref(false)
const projectPopoverOpen = ref(false)
const sidebarOpen = ref(false)
const projects = ref<ProjectSummary[]>([])
const projectName = ref('')
const theme = ref<'light' | 'dark'>(readInitialTheme())
const ROLE_LABEL: Record<AuthRole, string> = { admin: '管理员', developer: '开发者', operator: '分析师', viewer: '观察者' }
const accountLabel = computed(() => authAccount.value?.username ?? '会话用户')
const roleLabel = computed(() => authAccount.value ? ROLE_LABEL[authAccount.value.role] : '会话检测中')
const avatarText = computed(() => accountLabel.value.slice(0, 1).toUpperCase())

function readInitialTheme(): 'light' | 'dark' {
  const saved = globalThis.localStorage?.getItem('datara.theme')
  if (saved === 'dark' || saved === 'light') return saved
  return globalThis.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(next: 'light' | 'dark'): void {
  theme.value = next
  document.documentElement.dataset.theme = next
  globalThis.localStorage?.setItem('datara.theme', next)
}

function toggleTheme(): void {
  applyTheme(theme.value === 'light' ? 'dark' : 'light')
}

applyTheme(theme.value)

async function onLogout(): Promise<void> {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await logout()
    await router.replace('/login')
  } finally {
    loggingOut.value = false
  }
}

const isProjectScope = computed(() => route.path.startsWith('/p/'))
const projectId = computed<number | null>(() => {
  if (!isProjectScope.value) return null
  const raw = route.params.projectId
  const value = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isInteger(value) ? value : null
})

const activeProjectItem = computed(() => {
  const id = projectId.value
  if (id === null) return null
  return PROJECT_MENU_ITEMS.find((item) => projectItemPath(id, item) === route.path) ?? null
})

const breadcrumb = computed(() => activeProjectItem.value?.label ?? (isProjectScope.value ? '工作台' : '全局管理'))
let nameReqSeq = 0

async function loadProjectContext(): Promise<void> {
  const id = projectId.value
  if (id === null) return
  const seq = ++nameReqSeq
  try {
    const page = await listProjects()
    if (seq !== nameReqSeq) return
    projects.value = page.list
    projectName.value = page.list.find((project) => project.id === id)?.name ?? `项目 #${id}`
  } catch {
    if (seq !== nameReqSeq) return
    projects.value = []
    projectName.value = `项目 #${id}`
  }
}

async function selectProject(id: number): Promise<void> {
  projectPopoverOpen.value = false
  sidebarOpen.value = false
  rememberActiveProject(id)
  const segment = route.path.match(/^\/p\/[^/]+(\/.*)?$/)?.[1] ?? ''
  await router.push({ path: `/p/${id}${segment}`, query: route.query, hash: route.hash })
}

onMounted(() => {
  if (getToken() && !authAccount.value) void currentSession().catch(() => undefined)
})

watch([isProjectScope, projectId, authAccount], () => {
  nameReqSeq += 1
  projects.value = []
  projectName.value = ''
  projectPopoverOpen.value = false
  sidebarOpen.value = false
  if (isProjectScope.value) void loadProjectContext()
  else nameReqSeq += 1
}, { immediate: true })

function buildCtx(): MenuFilterContext {
  const resolved = router.getRoutes()
  // B5-d-3 四角色判定链接线：菜单过滤上下文携带当前角色的冻结权限集
  // （rolePermissions.ts ROLE_PERMISSIONS × authAccount.role；会话未就绪时空集 fail-closed）
  const role = authAccount.value?.role
  return {
    registeredRouteNames: new Set(resolved.map((record) => String(record.name ?? '')).filter(Boolean)),
    registeredPaths: new Set(resolved.map((record) => record.path)),
    permissions: new Set<string>(role ? ROLE_PERMISSIONS[role] : []),
    ...props.filterOverrides,
  }
}

const menuView = computed<readonly RenderableMenuGroup[]>(() => filterMenuGroups(buildCtx()))
const globalMounts = computed(() => filterGlobalMounts(buildCtx()))
const folded = reactive<Record<string, boolean>>({})
for (const group of menuGroups) folded[group.id] = loadGroupFolded(group.id, group.defaultFolded === true)
function onToggle(groupId: string): void {
  folded[groupId] = toggleGroupFolded(groupId, folded[groupId] ?? false)
}

const aiContext = computed(() => route.fullPath)
defineExpose({ menuView, aiContext })

/* ---- D5/G10 侧边栏拖宽（§7.1.7 超越项，用户裁定）：pointer 拖拽右缘把手 +
 * localStorage 持久化（datara.shell.sidebarWidth），钳制 200–420px；
 * 移动端 media query 单列布局覆盖，不受影响。 ---- */
const SIDEBAR_WIDTH_KEY = 'datara.shell.sidebarWidth'
const SIDEBAR_MIN_WIDTH = 200
const SIDEBAR_MAX_WIDTH = 420
const DEFAULT_SIDEBAR_WIDTH = 228

function readSidebarWidth(): number {
  const raw = globalThis.localStorage?.getItem(SIDEBAR_WIDTH_KEY)
  const value = Number(raw)
  return Number.isFinite(value) && value > 0
    ? Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, value))
    : DEFAULT_SIDEBAR_WIDTH
}

const sidebarWidth = ref(readSidebarWidth())

function onSidebarResizeStart(event: PointerEvent): void {
  if (event.button !== 0) return
  event.preventDefault()
  window.addEventListener('pointermove', onSidebarResizeMove)
  window.addEventListener('pointerup', onSidebarResizeEnd, { once: true })
}
function onSidebarResizeMove(event: PointerEvent): void {
  sidebarWidth.value = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, event.clientX))
}
function onSidebarResizeEnd(): void {
  window.removeEventListener('pointermove', onSidebarResizeMove)
  try { globalThis.localStorage?.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth.value)) } catch { /* 忽略隐私模式 */ }
}
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-open': sidebarOpen }" :style="{ '--sidebar-w': `${sidebarWidth}px` }">
    <aside class="app-sidebar" :class="{ open: sidebarOpen }" aria-label="主导航">
      <RouterLink to="/" class="brand" aria-label="Datara 项目管理">
        <span class="brand-mark">◆</span><span>Datara</span>
      </RouterLink>

      <nav v-if="isProjectScope" class="project-nav" aria-label="项目功能导航" data-project-nav>
        <section v-for="group in PROJECT_MENU_GROUPS" :key="group.id" class="project-menu-group" :data-project-group="group.id">
          <h2>{{ group.label }}</h2>
          <RouterLink
            v-for="item in group.items"
            :key="item.id"
            :to="projectItemPath(projectId!, item)"
            class="project-nav-link"
            :data-seg="item.id"
            @click="sidebarOpen = false"
          ><span class="ico">{{ item.icon }}</span><span class="lbl">{{ item.label }}</span></RouterLink>
        </section>
      </nav>

      <nav v-else class="global-nav" aria-label="全局功能导航">
        <div v-for="entry in menuView" :key="entry.group.id" class="menu-group" :data-group-id="entry.group.id">
          <div v-if="!entry.group.direct" class="group-title">
            <span>{{ entry.group.label }}</span>
            <button v-if="entry.group.foldable" type="button" :aria-expanded="!folded[entry.group.id]" @click="onToggle(entry.group.id)">{{ folded[entry.group.id] ? '▸' : '▾' }}</button>
          </div>
          <ul v-show="!entry.group.foldable || !folded[entry.group.id]" class="menu-items">
            <li v-for="item in entry.items" :key="item.id">
              <RouterLink v-if="item.path" :to="item.path" class="menu-link"><span class="ico">{{ item.icon }}</span><span class="lbl">{{ item.label }}</span></RouterLink>
            </li>
          </ul>
        </div>
      </nav>
      <p class="sidebar-foot">v3 · 数据治理工作台</p>
      <span class="sidebar-resize" aria-hidden="true" data-sidebar-resize @pointerdown="onSidebarResizeStart"></span>
    </aside>

    <header class="app-topbar">
      <button type="button" class="icon-button mobile-menu" data-sidebar-toggle :aria-expanded="sidebarOpen" aria-label="切换导航" @click="sidebarOpen = !sidebarOpen">☰</button>
      <div v-if="isProjectScope" class="project-switcher-wrap">
        <button type="button" class="project-switcher" data-project-switcher :aria-expanded="projectPopoverOpen" @click="projectPopoverOpen = !projectPopoverOpen">
          <span class="geo-dot"></span><strong :data-project-name="String(projectId)">{{ projectName }}</strong><span>⌄</span>
        </button>
        <div v-if="projectPopoverOpen" class="project-popover" role="menu">
          <button v-for="project in projects" :key="project.id" type="button" data-project-option :class="{ active: project.id === projectId }" @click="selectProject(project.id)">
            <span>{{ project.name }}</span><small>#{{ project.id }}</small>
          </button>
          <RouterLink v-if="projectId !== null" :to="`/p/${projectId}/system`" class="project-manage" data-project-members>成员管理 · 项目作用域</RouterLink>
          <RouterLink to="/" class="project-manage">项目管理 · 全局顶层</RouterLink>
        </div>
      </div>
      <RouterLink v-if="isProjectScope" to="/" class="project-manager-entry" data-project-exit>项目管理</RouterLink>
      <RouterLink v-else to="/" class="project-manager-entry" data-global-project>项目管理</RouterLink>

      <div class="breadcrumb"><b>{{ projectName || 'Datara' }}</b><span>/</span><span>{{ breadcrumb }}</span></div>
      <div class="topbar-actions">
        <RouterLink to="/dep/runtime" class="icon-button" data-global-operations title="部署运维" aria-label="部署运维">☁</RouterLink>
        <RouterLink to="/sys" class="icon-button" data-global-system title="系统管理" aria-label="系统管理">⚙</RouterLink>
        <button type="button" class="icon-button" data-theme-toggle :title="theme === 'dark' ? '切换浅色主题' : '切换深色主题'" @click="toggleTheme">{{ theme === 'dark' ? '☀' : '☾' }}</button>
        <div class="user-chip" data-current-user>
          <span class="avatar">{{ avatarText }}</span><span class="user-copy"><b>{{ accountLabel }}</b><small>{{ roleLabel }}</small></span>
          <button type="button" class="logout-button" data-shell-logout :disabled="loggingOut" @click="onLogout">{{ loggingOut ? '…' : '退出登录' }}</button>
        </div>
      </div>
    </header>

    <main class="app-content"><RouterView /></main>
    <button v-if="sidebarOpen" type="button" class="sidebar-backdrop" aria-label="关闭导航" @click="sidebarOpen = false"></button>
    <AiAssistantPanel v-if="globalMounts.length > 0" id="ai-assistant-global-mount" aria-label="AI 助手全局挂载点" :page-context="aiContext" :project-id="projectId" />
  </div>
</template>

<style scoped>
.app-shell{display:grid;grid-template:"aside header" 48px "aside main" minmax(0,1fr)/var(--sidebar-w,228px) minmax(0,1fr);height:100vh;overflow:hidden;background:var(--bg);color:var(--text)}
.app-sidebar{grid-area:aside;position:relative;display:flex;flex-direction:column;min-height:0;background:linear-gradient(180deg,#0b1c33,#08182c 64%,#0c2135);color:var(--sidebar-text);z-index:30}
.sidebar-resize{position:absolute;top:0;right:-3px;width:6px;height:100%;cursor:col-resize;touch-action:none;z-index:40}
.sidebar-resize:hover{background:rgba(255,255,255,.14)}
.brand{height:56px;display:flex;align-items:center;gap:10px;padding:0 18px;color:#fff;font-size:15px;font-weight:700;letter-spacing:.3px;border-bottom:1px solid rgba(255,255,255,.07)}
.brand-mark{display:grid;place-items:center;width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,var(--primary),var(--purple));box-shadow:0 4px 14px rgba(22,104,220,.35);font-size:11px}
.project-nav,.global-nav{flex:1;min-height:0;overflow:auto;padding:8px 0 18px}
.project-menu-group h2,.group-title{margin:0;padding:13px 26px 5px;color:#5f7d9e;font-size:10px;font-weight:700;letter-spacing:1.1px;text-transform:uppercase}
.project-nav-link,.menu-link{display:flex;align-items:center;gap:10px;margin:2px 10px;padding:7px 12px;border-radius:8px;color:var(--sidebar-text);font-size:12.5px;line-height:20px}
.project-nav-link:hover,.menu-link:hover{background:rgba(255,255,255,.07);color:#fff}
.project-nav-link.router-link-exact-active{color:#fff;background:linear-gradient(90deg,rgba(22,104,220,.95),rgba(65,116,223,.7));box-shadow:0 3px 12px rgba(0,87,210,.28)}
.ico{width:18px;text-align:center;flex:0 0 18px}.lbl{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.menu-items{list-style:none}.group-title{display:flex;justify-content:space-between}.group-title button{border:0;background:none;color:inherit}
.sidebar-foot{padding:12px 18px;color:#527293;font-size:10.5px;border-top:1px solid rgba(255,255,255,.06)}
.app-topbar{grid-area:header;display:flex;align-items:center;gap:12px;min-width:0;padding:0 16px;background:var(--card);border-bottom:1px solid var(--border);box-shadow:0 1px 2px rgba(16,24,40,.03);z-index:20}
.project-switcher-wrap{position:relative}.project-switcher{display:flex;align-items:center;gap:8px;max-width:310px;height:32px;padding:0 11px;border:1px solid var(--border-strong);border-radius:8px;background:var(--card);color:var(--text);cursor:pointer}.project-switcher strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12.5px}.geo-dot{width:7px;height:7px;border-radius:2px;background:linear-gradient(135deg,var(--primary),var(--purple));flex:0 0 auto}
.project-popover{position:absolute;top:38px;left:0;width:280px;padding:7px;background:var(--card);border:1px solid var(--border);border-radius:10px;box-shadow:var(--shadow-lg);z-index:60}.project-popover button{display:flex;justify-content:space-between;width:100%;padding:8px;border:0;border-radius:7px;background:none;color:var(--text);text-align:left;cursor:pointer}.project-popover button:hover,.project-popover button.active{background:var(--primary-light);color:var(--primary)}.project-popover small{color:var(--text-3)}.project-manage{display:block;margin-top:5px;padding:8px;border-top:1px solid var(--border);font-size:12px}
.breadcrumb{display:flex;align-items:center;gap:7px;min-width:0;color:var(--text-3);font-size:12px}.breadcrumb::before{content:'';width:3px;height:14px;border-radius:2px;background:linear-gradient(var(--primary),var(--purple))}.breadcrumb b{max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)}
.topbar-actions{display:flex;align-items:center;gap:7px;margin-left:auto}.icon-button{display:grid;place-items:center;width:30px;height:30px;padding:0;border:1px solid var(--border);border-radius:7px;background:var(--card);color:var(--text-2);cursor:pointer}.icon-button:hover{border-color:var(--primary);color:var(--primary)}.mobile-menu{display:none}
.user-chip{display:flex;align-items:center;gap:7px;height:34px;padding:0 7px;border:1px solid var(--border);border-radius:9px;background:var(--card)}.avatar{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:linear-gradient(135deg,var(--primary),var(--cyan));color:#fff}.user-copy{display:flex;flex-direction:column;line-height:1.05}.user-copy b{font-size:11px}.user-copy small{font-size:8px;color:var(--danger)}.logout-button{border:0;background:none;color:var(--text-3);font-size:10px;cursor:pointer}
.app-content{grid-area:main;min-width:0;min-height:0;overflow:auto;background:var(--bg)}.sidebar-backdrop{display:none}
@media(max-width:767px){
  .app-shell{grid-template:"header" 48px "main" minmax(0,1fr)/minmax(0,1fr)}.app-sidebar{position:fixed;inset:0 auto 0 0;width:min(86vw,288px);transform:translateX(-102%);transition:transform .2s var(--ease);box-shadow:var(--shadow-xl)}.app-sidebar.open{transform:translateX(0)}.mobile-menu{display:grid}.sidebar-backdrop{display:block;position:fixed;inset:0;border:0;background:rgba(6,16,30,.48);z-index:25}.project-switcher{max-width:110px}.breadcrumb{display:none}.project-manager-entry{display:none}.user-chip .avatar,.user-copy{display:none}.user-chip{padding:0 4px}.logout-button{display:inline-flex;align-items:center;justify-content:center;min-height:32px;padding:0 6px}.topbar-actions{gap:4px}.app-topbar{gap:6px;padding:0 8px}
}
</style>

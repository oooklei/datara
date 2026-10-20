<script setup lang="ts">
/**
 * AppShell 三段式布局组件（增量 2 / 票 2-05；L3-03 s251 增补项目模式分流）
 *
 * 蓝本：0.8 方案 §6（AI 全局挂载规则）/ §7 落点表（AppShell.vue 职责=三段式布局、
 * 菜单消费、AI 全局挂载）；权威设计 §4.1 L304（页面布局骨架=§4 抄袭范畴，§5D 语义复刻）；
 * 0.7 §2.2 节点 8（增量 1 最小壳填充承接）。
 * L3-03 增补（权威设计 §3.3 L571/L575）：route.path 以 /p/ 前缀互斥分流——
 *  - 项目模式：侧栏渲染七段功能导航（PROJECT_MENU_SECTIONS 同源消费，段名定稿
 *    navigation/projectMenu.ts），顶栏呈现当前项目名（listProjects 按 id 匹配）与
 *    返回项目列表链接；项目名请求带序号守卫（nameReqSeq）防项目切换乱序串显。
 *  - 全局模式：菜单消费/AI 挂载/折叠行为语义完全保持（增量 2 验收锚零变化）。
 * 纪律：
 *  - 菜单唯一消费 filterMenuGroups（2-02），组件零散落显隐判断；折叠接驳 groupFold（2-04）
 *  - AI 挂载点与 <RouterView/> 同级、单实例、登录页不挂载（登录页不进本组件——App.vue 守门）
 *  - 菜单显隐不替代鉴权：路由守卫（router/index.ts）仍是访问控制真源（L3-05 落守卫）
 *  - filterOverrides 仅测试/后续增量注入用；生产缺省走 BATCH_SWITCHES 保守关闭（R-15）
 */
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  filterGlobalMounts,
  filterMenuGroups,
  type MenuFilterContext,
  type RenderableMenuGroup,
} from '../navigation/filterMenu'
import { PROJECT_MENU_SECTIONS } from '../navigation/projectMenu'
import { loadGroupFolded, toggleGroupFolded } from '../navigation/groupFold'
import { menuGroups } from '../navigation/menu'
import { listProjects } from '../services/rebuild/projectApi'

const props = defineProps<{
  /** 测试/后续增量注入覆盖（如批次开关/预览许可）；生产不传，走 R-15 保守关闭 */
  filterOverrides?: Partial<MenuFilterContext>
}>()

const route = useRoute()
const router = useRouter()

// ---- 项目模式判定与顶栏项目名（L3-03；守卫归属校验归 L3-05 路由守卫） ----
const isProjectScope = computed(() => route.path.startsWith('/p/'))
const projectId = computed<number | null>(() => {
  if (!isProjectScope.value) return null
  const raw = route.params.projectId
  const n = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isInteger(n) ? n : null
})

const projectName = ref('')
// 竞态守卫：连续切换项目时旧请求返回序号已过期，直接丢弃防乱序串显
let nameReqSeq = 0

async function loadProjectName(): Promise<void> {
  const id = projectId.value
  if (id === null) return
  const seq = ++nameReqSeq
  try {
    const page = await listProjects()
    if (seq !== nameReqSeq) return
    const hit = page.list.find((p) => p.id === id)
    projectName.value = hit?.name ?? `项目 #${id}`
  } catch {
    if (seq !== nameReqSeq) return
    projectName.value = `项目 #${id}`
  }
}

watch(
  [isProjectScope, projectId],
  () => {
    if (isProjectScope.value) void loadProjectName()
    else projectName.value = ''
  },
  { immediate: true },
)

function buildCtx(): MenuFilterContext {
  const resolved = router.getRoutes()
  return {
    registeredRouteNames: new Set(resolved.map((r) => String(r.name ?? '')).filter((s) => s !== '')),
    registeredPaths: new Set(resolved.map((r) => r.path)),
    // RBAC 归增量 15：未配置 permission 的项视为通过（0.8 §2.2 门五）
    permissions: new Set<string>(),
    ...props.filterOverrides,
  }
}

const menuView = computed<readonly RenderableMenuGroup[]>(() => filterMenuGroups(buildCtx()))
const globalMounts = computed(() => filterGlobalMounts(buildCtx()))

// 折叠态初始化：组 id 稳定键读取（2-04），future 组缺省 defaultFolded:true
const folded = reactive<Record<string, boolean>>({})
for (const g of menuGroups) folded[g.id] = loadGroupFolded(g.id, g.defaultFolded === true)

function onToggle(groupId: string): void {
  folded[groupId] = toggleGroupFolded(groupId, folded[groupId] ?? false)
}

// AI 上下文随路由元信息更新（0.8 §6 规则 3；挂载点跨路由保持不重建）
const aiContext = computed(() => route.fullPath)

defineExpose({ menuView, aiContext })
</script>

<template>
  <div class="app-shell">
    <header class="app-topbar">
      <span class="topbar-brand">Datara</span>
      <span v-if="isProjectScope" class="topbar-project">
        <span class="topbar-project-name" :data-project-name="String(projectId)">{{ projectName }}</span>
        <RouterLink to="/" class="topbar-project-exit" data-project-exit>返回项目列表</RouterLink>
      </span>
    </header>
    <aside class="app-sidebar" aria-label="主导航">
      <nav
        v-if="isProjectScope"
        class="project-nav"
        aria-label="项目功能导航"
        data-project-nav
      >
        <RouterLink
          v-for="seg in PROJECT_MENU_SECTIONS"
          :key="seg.key"
          :to="`/p/${projectId}/${seg.key}`"
          class="project-nav-link"
          :data-seg="seg.key"
        >{{ seg.label }}</RouterLink>
      </nav>
      <template v-else>
      <div
        v-for="entry in menuView"
        :key="entry.group.id"
        class="menu-group"
        :data-group-id="entry.group.id"
      >
        <div v-if="!entry.group.direct" class="group-title">
          <span class="group-label">{{ entry.group.label }}</span>
          <button
            v-if="entry.group.foldable"
            type="button"
            class="group-toggle"
            :aria-expanded="!folded[entry.group.id]"
            @click="onToggle(entry.group.id)"
          >{{ folded[entry.group.id] ? '▸' : '▾' }}</button>
        </div>
        <ul v-show="!entry.group.foldable || !folded[entry.group.id]" class="menu-items">
          <li v-for="item in entry.items" :key="item.id" class="menu-item">
            <RouterLink v-if="item.path" :to="item.path" class="menu-link">{{ item.label }}</RouterLink>
            <span v-else class="menu-plain">{{ item.label }}</span>
          </li>
        </ul>
      </div>
      </template>
    </aside>
    <main class="app-content"><RouterView /></main>
    <div
      v-if="globalMounts.length > 0"
      id="ai-assistant-global-mount"
      aria-label="AI 助手全局挂载点"
    ></div>
  </div>
</template>

<style scoped>
/* 三段式 grid（增量 1 最小壳语义保持：header/aside/main） */
.app-shell{display:grid;grid-template:"header header" 56px "aside main" 1fr/240px 1fr;min-height:100vh}
.app-topbar{grid-area:header;display:flex;align-items:center;gap:16px;padding:0 16px}
.topbar-brand{font-weight:700}
.topbar-project{display:flex;align-items:center;gap:12px;margin-left:auto}
.topbar-project-name{font-weight:600}
.app-sidebar{grid-area:aside;overflow-y:auto}
.app-content{grid-area:main;min-width:0}
/* 菜单组渲染（0.8 §7：空组标题不显示由 v-if=!direct 保证；future 组 caret 折叠语义复刻） */
.group-title{display:flex;align-items:center;justify-content:space-between}
.menu-items{list-style:none;margin:0;padding:0}
.menu-item{line-height:32px}
.menu-link,.menu-plain{display:block;padding:0 12px}
/* 项目模式七段导航（L3-03）：与全局菜单互斥渲染，DOM 锚 data-project-nav/data-seg */
.project-nav{display:flex;flex-direction:column;padding:8px 0}
.project-nav-link{display:block;padding:0 12px;line-height:32px}
</style>

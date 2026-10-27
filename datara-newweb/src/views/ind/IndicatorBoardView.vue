<template>
  <main class="pg" aria-label="指标看板">
    <header class="pg-head">
      <h1 class="sec-head">指标看板</h1>
      <p class="pg-desc">指标定义的总览看板（governance metrics）。</p>
    </header>

    <div class="toolbar">
      <span class="spacer"></span>
      <span v-if="projectId !== null" class="hint">共 {{ page.total }} 条</span>
    </div>

    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="loading" @click="retry">重试</button>
    </div>

    <div v-if="loading" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:42%"></div>
      <div class="skeleton sk-row" style="width:78%"></div>
    </div>

    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">在上方下拉框选择项目后，即可加载指标看板。</div>
    </div>

    <div v-else-if="page.list.length === 0" class="panel empty" data-empty>
      <div class="e-title">暂无指标</div>
      <div class="e-hint">当前项目下还没有指标定义，请先在「指标目录」创建。</div>
    </div>

    <template v-else>
      <!-- 列表工具栏（对标旧版 .tbl-toolbar + .sec-head + .spacer + op-btn 入口） -->
      <div class="tbl-toolbar">
        <span class="sec-head">指标定义</span>
        <span class="pill info">{{ page.list.length }} 项</span>
        <span class="spacer"></span>
        <button type="button" class="op-btn" data-goto-list @click="gotoList">指标目录</button>
        <button type="button" class="op-btn" data-goto-consistency @click="gotoConsistency">一致性检查</button>
      </div>

      <!-- 两栏：左 指标定义卡（对标旧版 .board-grid 1.5fr）/ 右 状态分布 -->
      <section class="board-grid" data-ind-board>
        <div class="board-main">
          <article v-for="m in page.list" :key="m.id" class="board-card">
            <div class="b-t">{{ m.name }}</div>
            <div class="b-code mono">{{ m.code }}</div>
            <div class="b-formula">{{ m.formula }}</div>
            <div class="b-ft">
              <span class="st" :class="statusClass(m.status)"><span class="dot"></span>{{ statusLabel(m.status) }}</span>
              <span class="pill" :data-status="m.status">{{ statusLabel(m.status) }}</span>
            </div>
          </article>
        </div>

        <aside class="board-side">
          <div class="panel">
            <div class="panel-hd"><span class="sec-head">状态分布</span></div>
            <!-- 环形图（对标旧版 IndBoardView 的 conic-gradient donut + legend 范式；数据取真实状态分布，非演示数据） -->
            <div class="donut-wrap" data-ind-donut>
              <div class="donut" :style="{ background: donutGradient }">
                <div class="donut-center">
                  <b>{{ page.list.length }}</b>
                  <span>指标总数</span>
                </div>
              </div>
              <div class="legend">
                <div v-for="s in dist" :key="s.key" class="legend-line">
                  <span class="dot" :style="{ background: s.color }"></span>
                  <span>{{ s.label }}</span>
                  <span class="legend-val mono">{{ s.count }}</span>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  governanceApi,
  type DefinitionStatus,
  type MetricPage,
} from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const router = useRouter()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const page = ref<MetricPage>({ total: 0, list: [] })
const loading = ref(false)
const error = ref('')
/** 错误框「重试」绑定操作：按错误来源设定（默认重载看板），避免重试错配 */
const retry = ref<() => void>(() => reload)

const routeProjectId = computed<number | null>(() => {
  const raw = route.params.projectId ?? route.query.projectId
  const value = Array.isArray(raw) ? raw[0] : raw
  const n = Number(value)
  return value !== undefined && value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const projectId = computed<number | null>(() => {
  const fromRoute = routeProjectId.value
  if (fromRoute !== null) return fromRoute
  const n = Number(selectedProject.value)
  return selectedProject.value !== '' && Number.isInteger(n) && n > 0 ? n : null
})

const countOf = (s: DefinitionStatus): number => page.value.list.filter((m) => m.status === s).length
/** 状态分布（真实计数）→ 环形图 + 图例；状态为契约冻结枚举 draft/active/retired，不造演示数据 */
const DIST_META: { key: DefinitionStatus; label: string; color: string }[] = [
  { key: 'active', label: '启用中', color: 'var(--success)' },
  { key: 'draft', label: '草稿', color: 'var(--warn)' },
  { key: 'retired', label: '已停用', color: 'var(--text-3)' },
]
const dist = computed(() => DIST_META.map((m) => ({ ...m, count: countOf(m.key) })))
const donutGradient = computed<string>(() => {
  const total = page.value.list.length || 1
  let acc = 0
  const segs = dist.value.map((s) => {
    const from = (acc / total) * 100
    acc += s.count
    const to = (acc / total) * 100
    return `${s.color} ${from.toFixed(2)}% ${to.toFixed(2)}%`
  })
  return `conic-gradient(${segs.join(',')})`
})
const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))
const statusClass = (s: DefinitionStatus): string =>
  s === 'active' ? 'st-green' : s === 'retired' ? 'st-gray' : 'st-orange'
const statusLabel = (s: DefinitionStatus): string =>
  s === 'active' ? '启用中' : s === 'retired' ? '已停用' : '草稿'

/** 真实路由入口（routes.ts 已登记），非死链 */
function projectQuery(): Record<string, string> { return projectId.value === null ? {} : { projectId: String(projectId.value) } }
function gotoList(): void { router.push({ path: '/ind/list', query: projectQuery() }) }
function gotoConsistency(): void { router.push({ path: '/ind/consistency', query: projectQuery() }) }

async function init(): Promise<void> {
  try {
    const p = await listProjects()
    projects.value = p.list
    if (routeProjectId.value !== null) selectedProject.value = String(routeProjectId.value)
    if (selectedProject.value) await reload()
  } catch (e) {
    error.value = message(e)
    retry.value = init
  }
}
onMounted(init)

let reqSeq = 0
async function reload(): Promise<void> {
  if (projectId.value === null) { page.value = { total: 0, list: [] }; return }
  const seq = ++reqSeq
  loading.value = true
  error.value = ''
  try {
    const data = await governanceApi.listMetrics(projectId.value)
    if (seq !== reqSeq) return
    page.value = data
  } catch (e) { if (seq === reqSeq) error.value = message(e) }
  finally { if (seq === reqSeq) loading.value = false }
}
</script>

<style scoped>
/* 设计令牌：由全局 styles/theme.css 的 :root 提供（§4.4.3 风格统一），本文件不再就地重复定义。 */
/* 对标旧版 IndBoardView：两栏 board-grid（1.5fr / 1fr），左定义卡、右状态分布 */
.board-grid{grid-template-columns:1.5fr 1fr;align-items:start}
.board-main{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
/* 环形图（对标旧版 IndBoardView scoped 取值：150px donut + 96px center + legend） */
.donut-wrap{display:flex;gap:16px;align-items:center}
.donut{width:150px;height:150px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center}
.donut-center{width:96px;height:96px;border-radius:50%;background:var(--card);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px}
.donut-center b{font-size:17px}
.donut-center span{font-size:10px;color:var(--text-3)}
.legend{flex:1;display:flex;flex-direction:column;gap:7px}
.legend-line{display:flex;align-items:center;gap:7px;font-size:12px}
.legend-line .dot{width:9px;height:9px;border-radius:3px;flex-shrink:0}
.legend-val{margin-left:auto;color:var(--text-2);font-size:11.5px}
</style>

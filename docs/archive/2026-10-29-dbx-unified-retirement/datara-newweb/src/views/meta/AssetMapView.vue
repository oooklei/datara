<template>
  <main class="pg" aria-label="资产地图">
    <header class="pg-head">
      <h1 class="sec-head">资产地图</h1>
      <p class="pg-desc">多维归类浏览数据资产（projects/{id}/assets）。</p>
    </header>

    <div class="toolbar">
      <label class="field"><span>关键字</span>
        <input v-model.trim="keyword" class="kw" placeholder="资产名/描述" :disabled="loading" @keyup.enter="reload">
      </label>
      <button type="button" class="tb-new" :disabled="projectId === null || loading" @click="reload">查询</button>
      <button type="button" class="op-btn" :disabled="projectId === null || loading" @click="reset">重置</button>
      <span class="spacer"></span>
      <span v-if="projectId !== null" class="hint">共 {{ page.total }} 条</span>
    </div>

    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="loading" @click="retry">重试</button>
    </div>

    <div v-if="loading" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:45%"></div>
      <div class="skeleton sk-row" style="width:80%"></div>
      <div class="skeleton sk-row" style="width:65%"></div>
    </div>

    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">在上方下拉框选择项目后，即可加载资产地图。</div>
    </div>

    <div v-else-if="page.list.length === 0" class="panel empty" data-empty>
      <div class="e-title">暂无资产</div>
      <div class="e-hint">当前项目下没有匹配的资产，请调整关键字后重试。</div>
    </div>

    <template v-else>
      <div class="map-toolbar">
        <div class="seg" data-asset-views role="tablist" aria-label="归类视角">
          <button :class="{ on: view === 'domain' }" @click="setView('domain')">按业务域</button>
          <button :class="{ on: view === 'system' }" @click="setView('system')">按来源系统</button>
          <button :class="{ on: view === 'category' }" @click="setView('category')">按模块</button>
          <button :class="{ on: view === 'box' }" @click="setView('box')">框图</button>
        </div>
        <span class="hint">
          {{ domains.length }} 个业务域 · {{ systems.length }} 个来源系统 · 共 {{ fmt(page.total) }} 行
        </span>
      </div>

      <div class="map-body">
        <!-- 按业务域 -->
        <section v-if="view === 'domain'" data-asset-groups>
          <div class="legend">按业务域归类 · 组标题 = 业务域（色点） · 卡片 = 资产名 / 类型 / 负责人 / 质量分入口</div>
          <div class="cols">
            <div v-for="g in domainGroups" :key="g.name" class="col">
              <div class="col-head">
                <span class="dot" :style="{ background: g.color }" />
                <b>{{ g.name }}</b>
                <span class="cnt">{{ g.items.length }} 个</span>
              </div>
              <div class="col-desc">{{ g.desc || '未填写业务域说明' }}</div>
              <div v-for="a in g.items" :key="a.id" class="tbl-card">
                <div class="tbl-name mono" @click="goCatalog">{{ a.displayName || a.assetName }}</div>
                <div class="tbl-meta">
                  <span>{{ a.assetType }}</span>
                  <span>{{ a.ownerName || '—' }}</span>
                  <button type="button" class="score-btn" :disabled="!g.hasQuality" @click="goScore(a)">质量分</button>
                </div>
              </div>
            </div>
          </div>
          <div class="lock-tip">业务域取自资产的主题域归属（projects/{id}/assets 的 domain 字段）；如需调整归属，请在元数据目录中维护。</div>
        </section>

        <!-- 按来源系统 -->
        <section v-else-if="view === 'system'" data-asset-groups>
          <div class="legend">按来源系统归类 · 每个来源系统一列 · 卡片 = 资产名 / 类型 / 库 / 质量分入口</div>
          <div class="cols">
            <div v-for="g in systemGroups" :key="g.key" class="col">
              <div class="col-head">
                <span class="layer-tag" :style="{ background: g.color + '18', color: g.color }">{{ g.key }}</span>
                <span class="cnt">{{ g.items.length }} 个</span>
              </div>
              <div v-for="a in g.items" :key="a.id" class="tbl-card">
                <div class="tbl-name mono" @click="goCatalog">{{ a.displayName || a.assetName }}</div>
                <div class="tbl-meta">
                  <span>{{ a.databaseName }}</span>
                  <span>{{ a.assetType }}</span>
                  <button type="button" class="score-btn" :disabled="!g.hasQuality" @click="goScore(a)">质量分</button>
                </div>
              </div>
            </div>
          </div>
          <div class="lock-tip">后端当前未暴露数仓分层（ODS/DIM/DWD/DWS/ADS）端点，故以来源系统归组；分层口径待 warehouse model 端点开放后补齐。</div>
        </section>

        <!-- 按模块 -->
        <section v-else-if="view === 'category'" data-asset-groups>
          <div class="legend">按资产大类归类 · 数据表 / 指标 / 标准 · 每类卡片列出纳管样本与入口链接</div>
          <div class="cat-grid">
            <div v-for="c in categoryGroups" :key="c.name" class="cat-card">
              <div class="cat-head">
                <h3><span class="dot" :style="{ background: c.color }" />{{ c.name }}</h3>
                <span class="layer-tag" :style="{ background: c.color + '18', color: c.color }">{{ c.cnt }} {{ c.unit }}</span>
              </div>
              <div class="cat-body">
                <div v-for="it in c.items" :key="it" class="cat-item">
                  <span class="cat-ico">{{ c.ico }}</span>
                  <span class="mono">{{ it }}</span>
                </div>
                <div v-if="c.items.length === 0" class="cat-item">暂无纳管样本</div>
                <button v-if="c.link" type="button" class="cat-link" @click="c.link">{{ c.linkTxt }} →</button>
              </div>
            </div>
          </div>
          <div class="lock-tip">指标 / 标准数量来自对应列表接口（projects/{id}/metrics、projects/{id}/standards），仅在切换到本视角时加载；旧前端「报告」卡片为演示数据，后端未暴露报告端点，故不呈现。</div>
        </section>

        <!-- 框图 -->
        <section v-else data-asset-groups>
          <div class="legend">框图视图 · 大框 = 业务域（资产数 / 记录数） · 小框 = 资产（类型 / 行数 / 来源）</div>
          <div class="box-grid">
            <div v-for="g in boxGroups" :key="g.name" class="box-domain" :style="{ borderLeftColor: g.color }">
              <div class="box-head">
                <span class="dot" :style="{ background: g.color }" />
                <b>{{ g.name }}</b>
                <span class="box-stat">
                  <span class="box-badge">资产 {{ g.items.length }}</span>
                  <span class="box-badge">记录 {{ fmt(g.rows) }}</span>
                </span>
              </div>
              <div class="box-line2 box-stat">
                <span class="box-badge fact">表 {{ g.tables }}</span>
                <span class="box-badge dimb">视图 {{ g.views }}</span>
              </div>
              <div class="box-tbls">
                <div v-for="a in g.items" :key="a.id" class="box-tbl">
                  <div class="box-tbl-top">
                    <span class="tbl-name mono" @click="goCatalog">{{ a.displayName || a.assetName }}</span>
                    <span class="layer-tag" :style="{ background: g.color + '18', color: g.color }">{{ a.assetType }}</span>
                  </div>
                  <div class="box-tbl-meta">
                    <span>{{ a.rowCount ?? 0 }} 行</span>
                    <span class="box-engine">{{ a.sourceSystem }}</span>
                  </div>
                </div>
              </div>
              <div class="box-foot">
                <span class="box-foot-label">业务类型分布</span>
                <span v-if="g.chips.length" class="box-chips">
                  <span v-for="c in g.chips" :key="c.name" class="box-chip">{{ c.name }} {{ c.cnt }}</span>
                </span>
                <span v-else class="box-none">未标注类型</span>
              </div>
            </div>
          </div>
          <div class="lock-tip">口径：记录数 = 资产行数合计 · 表/视图按资产类型（assetType）判定；旧前端框图底部「码表标准（字典）」块依赖码表端点（后端仅 legacy 导入落库，未开放查询），故不呈现。</div>
        </section>

        <div class="panel">
          <div class="panel-hd">资产清单<span class="pill info">{{ page.list.length }}</span></div>
          <table class="tbl" data-asset-table>
            <thead><tr><th>资产</th><th>类型</th><th>来源</th><th>库</th><th>Schema</th><th>负责人</th><th>行数</th></tr></thead>
            <tbody>
              <tr v-for="a in page.list" :key="a.id">
                <td>{{ a.displayName || a.assetName }}</td>
                <td><span class="pill info">{{ a.assetType }}</span></td>
                <td>{{ a.sourceSystem }}</td>
                <td>{{ a.databaseName }}</td>
                <td>{{ a.schemaName || '—' }}</td>
                <td>{{ a.ownerName || '—' }}</td>
                <td class="mono">{{ a.rowCount ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { governanceApi, type AssetPage, type AssetRecord } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

type ViewKey = 'domain' | 'system' | 'category' | 'box'

const route = useRoute()
const router = useRouter()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const keyword = ref('')
const page = ref<AssetPage>({ total: 0, page: 1, pageSize: 50, list: [] })
const loading = ref(false)
const error = ref('')
const view = ref<ViewKey>('domain')
/** 按模块视角的指标/标准计数与样本：切到该视角时懒加载，失败不阻断主流程 */
const metricCnt = ref<number | null>(null)
const standardCnt = ref<number | null>(null)
const metricSamples = ref<string[]>([])
const standardSamples = ref<string[]>([])
type CategorySummary = { metricCnt: number | null; standardCnt: number | null; metricSamples: string[]; standardSamples: string[] }
const categoryCache = new Map<number, CategorySummary>()
/** 错误框「重试」绑定操作：按错误来源设定（默认重载资产，避免重试错配） */
const retry = ref<() => void>(() => reload)

let reqSeq = 0
let categorySeq = 0

const DOMAIN_COLORS = ['var(--primary)', 'var(--purple)', 'var(--cyan)', 'var(--success)', 'var(--warn)', 'var(--danger)']
const SYSTEM_COLORS = ['var(--primary)', 'var(--cyan)', 'var(--purple)', 'var(--success)', 'var(--warn)', 'var(--danger)', 'var(--cyan)']

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

/** 通用分组：按 keyOf 归桶并保持首次出现顺序（同旧前端按库聚合语义） */
function groupBy<T>(list: T[], keyOf: (item: T) => string) {
  const map = new Map<string, T[]>()
  for (const item of list) {
    const key = keyOf(item) || '未分组'
    const bucket = map.get(key)
    if (bucket) bucket.push(item)
    else map.set(key, [item])
  }
  return [...map.entries()].map(([key, items]) => ({ key, items }))
}

const domains = computed(() => groupBy(page.value.list, (a) => a.domainName))
const systems = computed(() => groupBy(page.value.list, (a) => a.sourceSystem))

const domainGroups = computed(() =>
  domains.value.map((g, i) => ({
    name: g.key,
    items: g.items,
    color: DOMAIN_COLORS[i % DOMAIN_COLORS.length],
    desc: '',
    hasQuality: g.items.some((a) => (a.qualityRuns?.length ?? 0) > 0),
  })),
)

const systemGroups = computed(() =>
  systems.value.map((g, i) => ({
    key: g.key,
    items: g.items,
    color: SYSTEM_COLORS[i % SYSTEM_COLORS.length],
    hasQuality: g.items.some((a) => (a.qualityRuns?.length ?? 0) > 0),
  })),
)

const boxGroups = computed(() =>
  domainGroups.value.map((g) => {
    const typeMap = new Map<string, number>()
    let rows = 0
    let tables = 0
    let views = 0
    for (const a of g.items) {
      const k = a.assetType || '未标注'
      typeMap.set(k, (typeMap.get(k) ?? 0) + 1)
      rows += a.rowCount ?? 0
      if (k === 'table') tables += 1
      else if (k === 'view') views += 1
    }
    return {
      name: g.name,
      color: g.color,
      items: g.items,
      rows,
      tables,
      views,
      chips: [...typeMap.entries()].map(([name, cnt]) => ({ name, cnt })),
    }
  }),
)

const categoryGroups = computed(() => {
  const list = page.value.list
  return [
    {
      name: '数据表',
      ico: '▤',
      color: 'var(--primary)',
      cnt: list.length,
      unit: '个',
      items: list.slice(0, 5).map((a) => a.displayName || a.assetName),
      link: goCatalog,
      linkTxt: '进入元数据目录',
    },
    {
      name: '指标',
      ico: '✦',
      color: 'var(--purple)',
      cnt: metricCnt.value ?? '—',
      unit: '项',
      items: metricSamples.value,
      link: () => router.push({ path: '/ind/list', query: projectId.value === null ? {} : { projectId: String(projectId.value) } }),
      linkTxt: '指标目录',
    },
    {
      name: '标准',
      ico: '§',
      color: 'var(--success)',
      cnt: standardCnt.value ?? '—',
      unit: '项',
      items: standardSamples.value,
      link: () => router.push({ path: '/std/element', query: projectId.value === null ? {} : { projectId: String(projectId.value) } }),
      linkTxt: '标准管理',
    },
  ]
})

const fmt = (n: number): string => (n >= 10000 ? (n / 10000).toFixed(n >= 1000000 ? 1 : 0) + '万' : String(n))

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

function setView(next: ViewKey) {
  view.value = next
  if (next === 'category') void loadCategoryCounts()
}

/** 懒加载指标/标准计数与样本：接口缺失或失败时保持 null（显示「—」），不影响主视图 */
async function loadCategoryCounts(): Promise<void> {
  const pid = projectId.value
  if (pid === null) return
  const cached = categoryCache.get(pid)
  if (cached) {
    applyCategorySummary(cached)
    return
  }
  const seq = ++categorySeq
  const safe = async (
    run: (() => Promise<unknown>) | undefined,
  ): Promise<{ total: number | null; names: string[] } | null> => {
    if (typeof run !== 'function') return null
    try {
      const res = (await run()) as { total?: number; list?: { name?: string }[] } | undefined
      const names = (res?.list ?? [])
        .map((x) => x.name)
        .filter((n): n is string => !!n)
      return { total: typeof res?.total === 'number' ? res.total : null, names }
    } catch {
      return null
    }
  }
  const [m, s] = await Promise.all([safe(() => governanceApi.listMetrics(pid, 1, 5)), safe(() => governanceApi.listStandards(pid, 1, 5))])
  const summary: CategorySummary = {
    metricCnt: m?.total ?? null,
    standardCnt: s?.total ?? null,
    metricSamples: m?.names ?? [],
    standardSamples: s?.names ?? [],
  }
  if (m !== null && s !== null) categoryCache.set(pid, summary)
  if (seq === categorySeq && projectId.value === pid) applyCategorySummary(summary)
}

function applyCategorySummary(summary?: CategorySummary): void {
  metricCnt.value = summary?.metricCnt ?? null
  standardCnt.value = summary?.standardCnt ?? null
  metricSamples.value = summary?.metricSamples ?? []
  standardSamples.value = summary?.standardSamples ?? []
}

function goCatalog() {
  const q = projectId.value !== null ? { projectId: String(projectId.value) } : {}
  router.push({ path: '/meta/catalog', query: q })
}

function goScore(a: AssetRecord) {
  void a
  const q = projectId.value !== null ? { projectId: String(projectId.value) } : {}
  router.push({ path: '/qc/report', query: q })
}

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

async function reload(): Promise<void> {
  const pid = projectId.value
  categorySeq += 1
  applyCategorySummary(pid === null ? undefined : categoryCache.get(pid))
  if (pid === null) {
    page.value = { total: 0, page: 1, pageSize: 50, list: [] }
    return
  }
  if (view.value === 'category' && !categoryCache.has(pid)) void loadCategoryCounts()
  const seq = ++reqSeq
  loading.value = true
  error.value = ''
  try {
    const data = await governanceApi.listAssets(pid, { q: keyword.value || undefined })
    if (seq !== reqSeq) return
    page.value = data
  } catch (e) {
    if (seq === reqSeq) {
      error.value = message(e)
      retry.value = reload
    }
  } finally {
    if (seq === reqSeq) loading.value = false
  }
}

function reset(): void {
  keyword.value = ''
  if (projectId.value !== null) void reload()
}
</script>

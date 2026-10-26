<template>
  <main class="pg" aria-label="元数据目录">
    <header class="pg-head">
      <h1 class="sec-head">元数据目录</h1>
      <p class="pg-desc">资产与字段清单（assets/{id} 明细）。</p>
    </header>

    <div class="toolbar">
      <label class="field"><span>项目</span>
        <select v-model="selectedProject" class="kw" data-project-select :disabled="loading || detailLoading" @change="reload">
          <option value="">请选择项目</option>
          <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
        </select>
      </label>
      <label class="field"><span>类型</span>
        <input v-model.trim="assetType" class="kw" placeholder="table/view" :disabled="loading || detailLoading" @keyup.enter="reload">
      </label>
      <button type="button" class="tb-new" :disabled="projectId === null || loading" @click="reload">查询</button>
      <span class="spacer"></span>
      <span v-if="projectId !== null" class="hint">共 {{ page.total }} 条</span>
    </div>

    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="loading || detailLoading" @click="retry">重试</button>
    </div>

    <div v-if="loading" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:38%"></div>
      <div class="skeleton sk-row" style="width:70%"></div>
      <div class="skeleton sk-row" style="width:54%"></div>
    </div>

    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">在上方下拉框选择项目后，即可加载元数据目录。</div>
    </div>

    <div v-else-if="page.list.length === 0" class="panel empty" data-empty>
      <div class="e-title">暂无资产</div>
      <div class="e-hint">当前项目下没有匹配的资产，请调整类型筛选后重试。</div>
    </div>

    <!-- 左筛选面板 + 右内容（对标旧前端 ListFilterPanel + .catalog 两栏） -->
    <div v-else class="split filter">
      <FilterPanel
        v-model:keyword="keyword"
        v-model:filters="filters"
        :facets="facets"
        placeholder="搜索资产"
        :result-count="filtered.length"
        :total-count="page.list.length"
      />

      <div class="page-main">
        <div class="panel">
          <div class="tbl-toolbar">
            <span class="sec-head">元数据目录</span>
            <span class="pill info">{{ filtered.length }} / {{ page.list.length }}</span>
            <span class="spacer"></span>
          </div>

          <div class="catalog">
            <aside class="tree" data-catalog-tree>
              <div class="node root" :class="{ active: filters.domain === '' }" @click="selectDomain('')">
                <span class="caret"></span>
                <span>全部</span>
                <span class="cnt">{{ page.list.length }}</span>
              </div>
              <div v-for="d in domains" :key="d.name" class="grp">
                <div class="node" :class="{ active: filters.domain === d.name }" @click="selectDomain(d.name)">
                  <span class="caret" :class="{ open: expanded.has(d.name) }" @click.stop="toggleDomain(d.name)">▸</span>
                  <span class="dot" :style="{ background: d.color }"></span>
                  <span>{{ d.name }}</span>
                  <span class="cnt">{{ d.count }}</span>
                </div>
                <div v-if="expanded.has(d.name)" class="kids">
                  <div
                    v-for="a in assetsOf(d.name)"
                    :key="a.id"
                    class="node leaf"
                    :class="{ active: selectedId === a.id }"
                    @click="select(a.id)"
                  >
                    <span class="caret"></span>
                    <span class="mono" style="font-size:11.5px">{{ a.assetName }}</span>
                  </div>
                </div>
              </div>
            </aside>

            <section class="list">
              <table class="tbl" data-catalog-list>
                <thead>
                  <tr>
                    <th>资产名</th><th>所属域</th><th>来源系统</th><th>类型</th>
                    <th>行数</th><th>负责人</th><th>更新时间</th><th style="width:140px">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="a in filtered" :key="a.id">
                    <td>
                      <button type="button" class="link-btn" :disabled="detailLoading" @click="select(a.id)">
                        <span class="mono" style="font-size:12px">{{ a.assetName }}</span>
                      </button>
                      <div style="color:var(--text-3);font-size:11px">{{ a.displayName || a.assetName }}</div>
                    </td>
                    <td><span class="pill info">{{ a.domainName || '—' }}</span></td>
                    <td style="color:var(--text-2)">{{ a.sourceSystem }}</td>
                    <td>{{ a.assetType }}</td>
                    <td class="mono">{{ a.rowCount ?? '—' }}</td>
                    <td>{{ a.ownerName || '—' }}</td>
                    <td style="color:var(--text-3)"><span class="mono" style="font-size:11.5px">{{ a.updatedAt || '—' }}</span></td>
                    <td>
                      <button type="button" class="op-btn primary" :disabled="detailLoading" @click="select(a.id)">详情</button>
                      <button type="button" class="op-btn" :disabled="detailLoading" @click="goLineage(a.id)">血缘</button>
                    </td>
                  </tr>
                  <tr v-if="filtered.length === 0">
                    <td class="empty" colspan="8">未找到匹配的元数据资产</td>
                  </tr>
                </tbody>
              </table>
            </section>
          </div>
        </div>

        <section class="panel" data-catalog-detail>
          <div v-if="detailLoading" role="status" aria-live="polite">
            <div class="skeleton sk-row" style="width:50%"></div>
            <div class="skeleton sk-row" style="width:84%"></div>
          </div>
          <template v-else-if="detail">
            <div class="panel-hd">{{ detail.displayName || detail.assetName }}<span class="pill info">{{ detail.assetType }}</span></div>
            <div class="result-line">
              <span class="code-chip">{{ detail.sourceSystem }}</span>
              <span class="mono">{{ detail.databaseName }}{{ detail.schemaName ? '.' + detail.schemaName : '' }}.{{ detail.assetName }}</span>
            </div>
            <div class="kv">
              <span class="k">id</span><span class="v mono">{{ detail.id }}</span>
              <span class="k">负责人</span><span class="v">{{ detail.ownerName || '—' }}</span>
              <span class="k">域</span><span class="v">{{ detail.domainName || '—' }}</span>
              <span class="k">行数</span><span class="v mono">{{ detail.rowCount ?? '—' }}</span>
            </div>
            <p class="hint">{{ detail.description || '无描述' }}</p>
            <div class="sub-hd" style="margin-top:12px">字段（{{ detail.fields?.length ?? 0 }}）</div>
            <table class="tbl" v-if="(detail.fields ?? []).length">
              <thead><tr><th>#</th><th>字段</th><th>类型</th><th>可空</th><th>描述</th></tr></thead>
              <tbody>
                <tr v-for="f in detail.fields ?? []" :key="f.id">
                  <td class="mono">{{ f.ordinalPosition }}</td>
                  <td class="mono">{{ f.fieldName }}</td>
                  <td><span class="pill info">{{ f.dataType }}</span></td>
                  <td><span class="pill" :class="f.nullable ? 'warn' : 'ok'">{{ f.nullable ? '是' : '否' }}</span></td>
                  <td>{{ f.description || '—' }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="hint">该资产暂无字段元数据。</p>
          </template>
          <p v-else class="hint">选择左侧资产查看字段明细。</p>
        </section>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FilterPanel, { type Facet } from '../../components/FilterPanel.vue'
import { governanceApi, type AssetPage } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const router = useRouter()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const assetType = ref('')
const page = ref<AssetPage>({ total: 0, page: 1, pageSize: 50, list: [] })
const detail = ref<AssetPage['list'][number] | null>(null)
const selectedId = ref<number | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const keyword = ref('')
const filters = ref<Record<string, string>>({})
const expanded = ref<Set<string>>(new Set())
/** 错误框「重试」绑定操作：按错误来源设定（默认重载列表，详情失败时重试详情） */
const retry = ref<() => void>(() => reload)
let reqSeq = 0
let detailSeq = 0

const DOMAIN_COLORS = ['var(--primary)', 'var(--purple)', 'var(--cyan)', 'var(--success)', 'var(--warn)', 'var(--danger)']

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

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return page.value.list.filter((a) => {
    if (filters.value.domain && a.domainName !== filters.value.domain) return false
    if (filters.value.assetType && a.assetType !== filters.value.assetType) return false
    if (!kw) return true
    const hay = `${a.assetName} ${a.displayName ?? ''} ${a.description ?? ''}`.toLowerCase()
    return hay.includes(kw)
  })
})

const facets = computed<Facet[]>(() => {
  const types = [...new Set(page.value.list.map((a) => a.assetType).filter(Boolean))].sort()
  const domainNames = domains.value.map((d) => d.name)
  return [
    { key: 'assetType', label: '类型', options: types.map((t) => ({ v: t, t })) },
    { key: 'domain', label: '业务域', options: domainNames.map((d) => ({ v: d, t: d })) },
  ]
})

const domains = computed(() => {
  const bucket = new Map<string, number>()
  for (const a of page.value.list) {
    const name = a.domainName || '未分组'
    bucket.set(name, (bucket.get(name) ?? 0) + 1)
  }
  return [...bucket.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([name, count], i) => ({ name, count, color: DOMAIN_COLORS[i % DOMAIN_COLORS.length] }))
})

function assetsOf(domain: string) {
  const name = domain || '未分组'
  return page.value.list.filter((a) => (a.domainName || '未分组') === name)
}

function selectDomain(name: string) {
  filters.value = { ...filters.value, domain: name }
}

function toggleDomain(name: string) {
  const next = new Set(expanded.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  expanded.value = next
}

function goLineage(assetId: number) {
  const q = projectId.value !== null ? { projectId: String(projectId.value), assetId: String(assetId) } : { assetId: String(assetId) }
  router.push({ path: '/meta/lineage', query: q })
}

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

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
  detail.value = null
  selectedId.value = null
  expanded.value = new Set()
  if (projectId.value === null) { page.value = { total: 0, page: 1, pageSize: 50, list: [] }; return }
  const seq = ++reqSeq
  loading.value = true
  error.value = ''
  try {
    const data = await governanceApi.listAssets(projectId.value, { assetType: assetType.value || undefined })
    if (seq !== reqSeq) return
    page.value = data
  } catch (e) {
    if (seq === reqSeq) {
      error.value = message(e)
      retry.value = reload
    }
  } finally { if (seq === reqSeq) loading.value = false }
}

async function select(id: number): Promise<void> {
  selectedId.value = id
  detail.value = null
  const seq = ++detailSeq
  detailLoading.value = true
  error.value = ''
  try {
    const data = await governanceApi.getAsset(id)
    if (seq !== detailSeq) return
    detail.value = data
  } catch (e) {
    if (seq === detailSeq) {
      error.value = message(e)
      retry.value = () => select(id)
    }
  } finally { if (seq === detailSeq) detailLoading.value = false }
}
</script>

<style scoped>
.link-btn{border:none;background:none;padding:0;color:var(--primary);cursor:pointer;text-align:left}
.link-btn:hover{text-decoration:underline}
.link-btn:disabled{opacity:.45;cursor:not-allowed}
</style>

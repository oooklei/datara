<template>
  <main class="pg" aria-label="指标目录">
    <header class="pg-head">
      <h1 class="sec-head">指标目录</h1>
      <p class="pg-desc">语义指标定义（governance metrics）。</p>
    </header>

    <div class="toolbar">
      <div class="ind-actions">
        <label class="field"><span>项目</span>
          <select v-model="selectedProject" class="kw" data-project-select :disabled="loading || saving" @change="reload">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
        <button type="button" class="tb-new" :disabled="projectId === null || saving" @click="openCreate">新建指标</button>
      </div>
      <span class="spacer"></span>
      <span v-if="projectId !== null" class="hint">共 {{ page.total }} 条</span>
    </div>

    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="loading || saving" @click="retry">重试</button>
    </div>

    <div v-if="loading" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:36%"></div>
      <div class="skeleton sk-row" style="width:76%"></div>
      <div class="skeleton sk-row" style="width:60%"></div>
    </div>

    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">在上方下拉框选择项目后，即可加载指标目录。</div>
    </div>

    <div v-else-if="page.list.length === 0" class="panel empty" data-empty>
      <div class="e-title">暂无指标</div>
      <div class="e-hint">当前项目下还没有指标定义，点击「新建指标」创建。</div>
    </div>

    <!-- 左筛选面板 + 右内容（对标旧前端 IndListView 的 ListFilterPanel 两栏范式） -->
    <div v-else class="split filter">
      <FilterPanel
        v-model:keyword="keyword"
        v-model:filters="filters"
        :facets="facets"
        placeholder="搜索指标"
        :result-count="filtered.length"
        :total-count="page.list.length"
      />

      <div class="page-main">
        <section class="panel">
          <div class="tbl-toolbar">
            <span class="sec-head">指标管理</span>
            <span class="pill info">{{ filtered.length }} / {{ page.list.length }}</span>
            <span class="spacer"></span>
            <button type="button" class="op-btn" :disabled="loading || saving" @click="gotoConsistency">一致性检查</button>
          </div>
          <table class="tbl" data-ind-list>
            <thead>
              <tr>
                <th>编码</th><th>名称</th><th>公式</th><th>描述</th>
                <th>状态</th><th>创建时间</th><th>更新时间</th><th style="width:150px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in filtered" :key="m.id">
                <td class="mono">{{ m.code }}</td>
                <td>{{ m.name }}</td>
                <td><span class="code-chip">{{ m.formula }}</span></td>
                <td style="font-size:11.5px;color:var(--text-2)">{{ m.description || '—' }}</td>
                <td><span class="st" :class="statusClass(m.status)"><span class="dot"></span>{{ statusLabel(m.status) }}</span></td>
                <td class="mono">{{ m.createdAt || '—' }}</td>
                <td class="mono">{{ m.updatedAt || '—' }}</td>
                <td>
                  <button type="button" class="op-btn primary" @click="detail = m">详情</button>
                  <button type="button" class="op-btn" @click="gotoBoard">趋势</button>
                </td>
              </tr>
              <tr v-if="filtered.length === 0">
                <td class="empty" colspan="8">未找到匹配的指标，请调整筛选条件</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </div>

    <div v-if="detail" class="drawer-mask" @click.self="closeDetail">
      <aside class="drawer" role="dialog" aria-modal="true" aria-label="指标详情">
        <div class="drawer-hd">{{ detail.name }}<button type="button" class="x" aria-label="关闭" @click="closeDetail">×</button></div>
        <div class="drawer-bd">
          <div class="kv">
            <span class="k">id</span><span class="v mono">{{ detail.id }}</span>
            <span class="k">编码</span><span class="v mono">{{ detail.code }}</span>
            <span class="k">状态</span><span class="v"><span class="st" :class="statusClass(detail.status)"><span class="dot"></span>{{ statusLabel(detail.status) }}</span></span>
            <span class="k">创建时间</span><span class="v mono">{{ detail.createdAt || '—' }}</span>
            <span class="k">更新时间</span><span class="v mono">{{ detail.updatedAt || '—' }}</span>
          </div>
          <div class="sub-hd" style="margin-top:12px">公式</div>
          <div class="board-card"><div class="b-formula">{{ detail.formula }}</div></div>
          <p class="hint" style="margin-top:8px">{{ detail.description || '无描述' }}</p>
        </div>
      </aside>
    </div>

    <div v-if="showCreate" class="mask" @click.self="closeCreate">
      <form ref="dlgEl" class="dlg" role="dialog" aria-modal="true" aria-label="新建指标" @submit.prevent="save">
        <div class="dlg-hd">新建指标<button type="button" class="x" aria-label="关闭" @click="closeCreate">×</button></div>
        <div class="dlg-bd">
          <div class="form-grid">
            <label class="f-item"><span>编码</span><input v-model.trim="form.code" required :disabled="saving"></label>
            <label class="f-item"><span>名称</span><input v-model.trim="form.name" required :disabled="saving"></label>
            <label class="f-item full"><span>公式</span><textarea v-model.trim="form.formula" required rows="3" :disabled="saving"></textarea></label>
            <label class="f-item"><span>描述</span><input v-model="form.description" :disabled="saving"></label>
            <label class="f-item"><span>状态</span>
              <select v-model="form.status" :disabled="saving">
                <option value="draft">draft</option>
                <option value="active">active</option>
                <option value="retired">retired</option>
              </select>
            </label>
          </div>
        </div>
        <div class="dlg-ft">
          <button type="button" class="op-btn" :disabled="saving" @click="closeCreate">取消</button>
          <button type="submit" class="tb-new" :disabled="saving || form.code === '' || form.name === '' || form.formula === ''">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </form>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FilterPanel, { type Facet } from '../../components/FilterPanel.vue'
import {
  governanceApi,
  type DefinitionStatus,
  type MetricDefinition,
  type MetricPage,
} from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const router = useRouter()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const page = ref<MetricPage>({ total: 0, list: [] })
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const showCreate = ref(false)
const detail = ref<MetricDefinition | null>(null)
const dlgEl = ref<HTMLFormElement | null>(null)
/** 错误框「重试」绑定操作：按错误来源设定（默认重载列表，保存失败时重试保存） */
const retry = ref<() => void>(() => reload)
const form = reactive({
  code: '',
  name: '',
  formula: '',
  description: '',
  status: 'draft' as DefinitionStatus,
})
/** 左筛选面板：关键字 + 各 facet 当前值（'' = 全部） */
const keyword = ref('')
const filters = ref<Record<string, string>>({})

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

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))
const statusClass = (s: DefinitionStatus): string =>
  s === 'active' ? 'st-green' : s === 'retired' ? 'st-gray' : 'st-orange'
const statusLabel = (s: DefinitionStatus): string =>
  s === 'active' ? '已发布' : s === 'retired' ? '已退役' : '草稿'

/** 状态为契约冻结枚举（draft/active/retired），facet 选项取自契约而非演示数据。 */
const facets = computed<Facet[]>(() => [
  { key: 'status', label: '状态', options: [
    { v: 'draft', t: '草稿' },
    { v: 'active', t: '已发布' },
    { v: 'retired', t: '已退役' },
  ] },
])

/** 客户端筛选（关键字 + 状态）；数据源为后端指标列表。 */
const filtered = computed<MetricDefinition[]>(() => {
  const kw = keyword.value.trim().toLowerCase()
  return page.value.list.filter((m) => {
    if (filters.value.status && m.status !== filters.value.status) return false
    if (!kw) return true
    return `${m.code} ${m.name} ${m.formula} ${m.description ?? ''}`.toLowerCase().includes(kw)
  })
})

/** 顶部/行内「一致性检查」「趋势」入口：跳转既有治理页面（真实路由）。 */
function gotoConsistency(): void {
  router.push({ path: '/ind/consistency', query: projectId.value === null ? {} : { projectId: String(projectId.value) } })
}
function gotoBoard(): void {
  router.push({ path: '/ind/board', query: projectId.value === null ? {} : { projectId: String(projectId.value) } })
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

function openCreate(): void {
  Object.assign(form, { code: '', name: '', formula: '', description: '', status: 'draft' })
  showCreate.value = true
  void nextTick(() => dlgEl.value?.querySelector('input')?.focus())
}

function closeCreate(): void {
  if (saving.value) return
  showCreate.value = false
}

function closeDetail(): void {
  detail.value = null
}

async function save(): Promise<void> {
  if (projectId.value === null || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await governanceApi.createMetric(projectId.value, { ...form })
    showCreate.value = false
    await reload()
  } catch (e) {
    error.value = message(e)
    retry.value = save
  } finally { saving.value = false }
}
</script>

<style scoped>
.ind-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
</style>

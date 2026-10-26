<template>
  <main class="pg" aria-label="标准管理">
    <header class="pg-head">
      <h1 class="sec-head">标准管理</h1>
      <p class="pg-desc">数据标准定义与结构校验（standards / standards/check）。</p>
    </header>

    <div class="toolbar">
      <div class="std-actions">
        <label class="field"><span>项目</span>
          <select v-model="selectedProject" class="kw" data-project-select @change="reload">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
        <button type="button" class="tb-new" :disabled="projectId === null || saving" @click="openCreate">新建标准</button>
      </div>
      <span class="spacer"></span>
      <span v-if="projectId !== null" class="hint">共 {{ page.total }} 条</span>
    </div>

    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="loading || saving || checkingId !== null" @click="retry">重试</button>
    </div>

    <div v-if="loading" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:34%"></div>
      <div class="skeleton sk-row" style="width:74%"></div>
      <div class="skeleton sk-row" style="width:58%"></div>
    </div>

    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">在上方下拉框选择项目后，即可加载标准定义。</div>
    </div>

    <div v-else-if="page.list.length === 0" class="panel empty" data-empty>
      <div class="e-title">暂无标准</div>
      <div class="e-hint">当前项目下还没有数据标准，点击「新建标准」创建。</div>
    </div>

    <!-- 左筛选面板 + 右内容（对标旧前端 datara-web StdElementView 的 ListFilterPanel 两栏表格页范式） -->
    <div v-else class="split filter">
      <FilterPanel
        v-model:keyword="keyword"
        v-model:filters="filters"
        :facets="facets"
        placeholder="搜索编码/名称"
        :result-count="filtered.length"
        :total-count="page.list.length"
      />

      <div class="page-main">
        <section class="panel">
          <div class="tbl-toolbar">
            <span class="sec-head">数据元标准</span>
            <span class="pill info">{{ filtered.length }} / {{ page.list.length }}</span>
            <span class="spacer"></span>
          </div>
          <table class="tbl" data-std-list>
            <thead><tr><th>编码</th><th>名称</th><th>数据类型</th><th>表达式</th><th>状态</th><th style="width:110px">操作</th></tr></thead>
            <tbody>
              <tr v-for="s in filtered" :key="s.id">
                <td class="mono">{{ s.code }}</td>
                <td>{{ s.name }}</td>
                <td><span class="pill info">{{ s.dataType }}</span></td>
                <td><span class="code-chip">{{ s.expression || '—' }}</span></td>
                <td><span class="st" :class="statusClass(s.status)"><span class="dot"></span>{{ statusLabel(s.status) }}</span></td>
                <td><button type="button" class="op-btn" :disabled="checkingId !== null" @click="check(s)">校验</button></td>
              </tr>
            </tbody>
          </table>
          <div v-if="filtered.length === 0" class="empty">未找到匹配的标准</div>
        </section>

        <section v-if="checkResult" class="panel" data-check-result>
          <div class="panel-hd">校验结果<span class="pill" :class="checkPassed ? 'ok' : 'err'">{{ checkPassed ? '通过' : '未通过' }}</span></div>
          <div class="result-line"><span class="code-chip">{{ checkResult.code }}</span><span class="mono">引擎 {{ checkResult.engine }}</span></div>
          <ul v-if="checkResult.findings.length" class="node-list" style="margin-top:8px">
            <li v-for="(f, i) in checkResult.findings" :key="i"><strong>发现 {{ i + 1 }}</strong><span>{{ describe(f) }}</span></li>
          </ul>
          <p v-else class="hint">未发现结构问题。</p>
          <p class="hint">校验时间：{{ checkResult.checkedAt || '—' }}</p>
        </section>
      </div>
    </div>

    <div v-if="showCreate" class="mask" @click.self="closeCreate">
      <form ref="dlgEl" class="dlg" role="dialog" aria-modal="true" aria-label="新建标准" @submit.prevent="save">
        <div class="dlg-hd">新建标准<button type="button" class="x" aria-label="关闭" @click="closeCreate">×</button></div>
        <div class="dlg-bd">
          <div class="form-grid">
            <label class="f-item"><span>编码</span><input v-model.trim="form.code" required :disabled="saving"></label>
            <label class="f-item"><span>名称</span><input v-model.trim="form.name" required :disabled="saving"></label>
            <label class="f-item"><span>数据类型</span><input v-model.trim="form.dataType" required placeholder="string/int/decimal" :disabled="saving"></label>
            <label class="f-item"><span>表达式</span><input v-model.trim="form.expression" placeholder="如 not_null / length<=64" :disabled="saving"></label>
            <label class="f-item"><span>描述</span><input v-model="form.description" :disabled="saving"></label>
            <label class="f-item"><span>状态</span>
              <select v-model="form.status" :disabled="saving">
                <option value="draft">草稿</option>
                <option value="active">生效</option>
                <option value="retired">停用</option>
              </select>
            </label>
          </div>
        </div>
        <div class="dlg-ft">
          <button type="button" class="op-btn" :disabled="saving" @click="closeCreate">取消</button>
          <button type="submit" class="tb-new" :disabled="saving || form.code === '' || form.name === '' || form.dataType === ''">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </form>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import FilterPanel, { type Facet } from '../../components/FilterPanel.vue'
import {
  governanceApi,
  type DefinitionStatus,
  type StandardCheckResult,
  type StandardDefinition,
  type StandardPage,
} from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const page = ref<StandardPage>({ total: 0, list: [] })
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const showCreate = ref(false)
const checkingId = ref<number | null>(null)
const checkResult = ref<StandardCheckResult | null>(null)
const dlgEl = ref<HTMLFormElement | null>(null)
/** 左筛选面板：关键字 + 状态 facet（'' = 全部） */
const keyword = ref('')
const filters = ref<Record<string, string>>({ status: '' })
/** 错误框「重试」绑定操作：按错误来源设定（默认重载列表，保存/校验失败时重试对应操作） */
const retry = ref<() => void>(() => reload)
const form = reactive({
  code: '',
  name: '',
  dataType: '',
  expression: '',
  description: '',
  status: 'draft' as DefinitionStatus,
})

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

const checkPassed = computed(() => checkResult.value?.passed === true)

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))
const statusClass = (s: DefinitionStatus): string =>
  s === 'active' ? 'st-green' : s === 'retired' ? 'st-gray' : 'st-orange'
const statusLabel = (s: DefinitionStatus): string =>
  s === 'active' ? '生效' : s === 'retired' ? '停用' : '草稿'
const describe = (f: unknown): string => (typeof f === 'string' ? f : JSON.stringify(f))

/** facet 选项取自契约 DefinitionStatus（draft/active/retired），而非演示数据。 */
const facets = computed<Facet[]>(() => [
  { key: 'status', label: '状态', options: [
    { v: 'draft', t: '草稿' },
    { v: 'active', t: '生效' },
    { v: 'retired', t: '停用' },
  ] },
])

/** 客户端筛选（关键字 + 状态）；数据源为后端标准列表。 */
const filtered = computed<StandardDefinition[]>(() => {
  const kw = keyword.value.trim().toLowerCase()
  const want = filters.value.status
  return page.value.list.filter((s) => {
    if (want !== '' && s.status !== want) return false
    if (!kw) return true
    return `${s.code} ${s.name} ${s.dataType}`.toLowerCase().includes(kw)
  })
})

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
  checkResult.value = null
  if (projectId.value === null) { page.value = { total: 0, list: [] }; return }
  const seq = ++reqSeq
  loading.value = true
  error.value = ''
  try {
    const data = await governanceApi.listStandards(projectId.value)
    if (seq !== reqSeq) return
    page.value = data
  } catch (e) {
    if (seq === reqSeq) {
      error.value = message(e)
      retry.value = reload
    }
  } finally { if (seq === reqSeq) loading.value = false }
}

function openCreate(): void {
  Object.assign(form, { code: '', name: '', dataType: '', expression: '', description: '', status: 'draft' })
  showCreate.value = true
  void nextTick(() => dlgEl.value?.querySelector('input')?.focus())
}

function closeCreate(): void {
  if (saving.value) return
  showCreate.value = false
}

async function save(): Promise<void> {
  if (projectId.value === null || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await governanceApi.createStandard(projectId.value, { ...form })
    showCreate.value = false
    await reload()
  } catch (e) {
    error.value = message(e)
    retry.value = save
  } finally { saving.value = false }
}

let checkSeq = 0
async function check(s: StandardDefinition): Promise<void> {
  if (projectId.value === null || checkingId.value !== null) return
  const seq = ++checkSeq
  checkingId.value = s.id
  error.value = ''
  try {
    const res = await governanceApi.checkStandard(projectId.value, { standardId: s.id })
    if (seq !== checkSeq) return
    checkResult.value = res[0] ?? null
  } catch (e) {
    if (seq === checkSeq) {
      error.value = message(e)
      retry.value = () => check(s)
    }
  } finally { if (seq === checkSeq) checkingId.value = null }
}
</script>

<style scoped>
/* 对标旧版 StdElementView：操作按钮集中于卡片头部工具栏，左筛选面板承载搜索与 facet */
.std-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
</style>

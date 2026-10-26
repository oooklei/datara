<template>
  <main class="pg" aria-label="一致性检查">
    <header class="pg-head">
      <h1 class="sec-head">一致性检查</h1>
      <p class="pg-desc">按标准执行结构校验（standards/check）。</p>
    </header>

    <div class="toolbar">
      <label class="field"><span>项目</span>
        <select v-model="selectedProject" class="kw" data-project-select :disabled="loading || running" @change="loadStandards">
          <option value="">请选择项目</option>
          <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
        </select>
      </label>
      <label class="field"><span>标准</span>
        <select v-model="selectedStd" class="kw" data-standard-select :disabled="standards.length === 0 || running">
          <option value="">请选择标准</option>
          <option v-for="s in standards" :key="s.id" :value="String(s.id)">{{ s.code }} - {{ s.name }}</option>
        </select>
      </label>
      <button type="button" class="tb-new" :disabled="projectId === null || selectedStd === '' || running" @click="runCheck">执行检查</button>
      <span class="spacer"></span>
      <span v-if="projectId !== null" class="hint">标准 {{ standards.length }} 条</span>
    </div>

    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="loading || running" @click="retry">重试</button>
    </div>

    <div v-if="loading" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:40%"></div>
      <div class="skeleton sk-row" style="width:72%"></div>
    </div>

    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">在上方下拉框选择项目后，即可加载标准并执行一致性检查。</div>
    </div>

    <template v-else>
      <div v-if="running" class="panel" role="status" aria-live="polite">
        <div class="skeleton sk-row" style="width:52%"></div>
        <div class="skeleton sk-row" style="width:80%"></div>
      </div>

      <div v-else-if="standards.length === 0" class="panel empty" data-no-standards>
        <div class="e-title">暂无标准</div>
        <div class="e-hint">当前项目下还没有标准定义，请先在「标准管理」创建后再执行一致性检查。</div>
      </div>

      <p v-else-if="!result" class="panel empty" data-pending>选择标准后执行检查。</p>
      <div v-else-if="results.length === 0" class="panel empty" data-empty>检查无返回</div>

      <!-- 左筛选面板 + 右内容（对标旧前端 IndConsistencyView 的 ListFilterPanel 两栏范式） -->
      <div v-else class="split filter">
        <FilterPanel
          v-model:keyword="keyword"
          v-model:filters="filters"
          :facets="facets"
          placeholder="搜索标准/编码"
          :result-count="filtered.length"
          :total-count="results.length"
        />

        <div class="page-main">
          <div class="stat-row">
            <div class="stat-card">
              <span class="type-icon" style="background:#1668dc">⇋</span>
              <div><div class="stat-num">{{ results.length }}</div><div class="stat-label">检查项数</div></div>
            </div>
            <div class="stat-card">
              <span class="type-icon" style="background:#16a34a">✓</span>
              <div><div class="stat-num" style="color:var(--success)">{{ passCount }}</div><div class="stat-label">通过</div></div>
            </div>
            <div class="stat-card">
              <span class="type-icon" style="background:#e5484d">✗</span>
              <div><div class="stat-num" style="color:var(--danger)">{{ failCount }}</div><div class="stat-label">未通过</div></div>
            </div>
          </div>

          <section class="panel" data-consistency-result>
            <div class="tbl-toolbar">
              <span class="sec-head">检查结果</span>
              <span class="pill info">{{ filtered.length }} / {{ results.length }}</span>
              <span class="spacer"></span>
              <button type="button" class="op-btn" data-goto-list @click="gotoList">指标目录</button>
            </div>
            <table class="tbl">
              <thead>
                <tr>
                  <th>标准</th><th>编码</th><th>结果</th><th>引擎</th><th>时间</th>
                  <th style="width:90px">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, i) in filtered" :key="r.standardId + '-' + i">
                  <td class="mono">#{{ r.standardId }}</td>
                  <td class="mono">{{ r.code }}</td>
                  <td>
                    <span class="st" :class="r.passed ? 'st-green' : 'st-red'">
                      <span class="dot"></span>{{ r.passed ? '通过' : '未通过' }}
                    </span>
                  </td>
                  <td>{{ r.engine }}</td>
                  <td class="mono">{{ r.checkedAt || '—' }}</td>
                  <td>
                    <button type="button" class="op-btn" @click="openDetail(r)">详情</button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-if="filtered.length === 0" class="empty">未找到匹配的检查结果</div>
          </section>
        </div>
      </div>
    </template>

    <div v-if="detail" class="drawer-mask" @click.self="closeDetail">
      <aside class="drawer" role="dialog" aria-modal="true" aria-label="检查结果详情">
        <div class="drawer-hd">
          检查结果 · {{ detail.code }}
          <button type="button" class="x" aria-label="关闭" @click="closeDetail">×</button>
        </div>
        <div class="drawer-bd">
          <div class="kv">
            <span class="k">标准</span><span class="v mono">#{{ detail.standardId }}</span>
            <span class="k">编码</span><span class="v mono">{{ detail.code }}</span>
            <span class="k">结果</span>
            <span class="v">
              <span class="st" :class="detail.passed ? 'st-green' : 'st-red'">
                <span class="dot"></span>{{ detail.passed ? '通过' : '未通过' }}
              </span>
            </span>
            <span class="k">引擎</span><span class="v">{{ detail.engine }}</span>
            <span class="k">检查时间</span><span class="v mono">{{ detail.checkedAt || '—' }}</span>
          </div>
          <div class="sub-hd" style="margin-top:12px">差异明细</div>
          <ul v-if="detail.findings.length" class="finding-list">
            <li v-for="(f, i) in detail.findings" :key="i" class="mono">{{ findingText(f) }}</li>
          </ul>
          <p v-else class="hint">无差异明细。</p>
        </div>
      </aside>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FilterPanel, { type Facet } from '../../components/FilterPanel.vue'
import {
  governanceApi,
  type StandardCheckResult,
  type StandardDefinition,
} from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const router = useRouter()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const standards = ref<StandardDefinition[]>([])
const selectedStd = ref('')
const results = ref<StandardCheckResult[]>([])
const result = ref<StandardCheckResult[] | null>(null)
const loading = ref(false)
const running = ref(false)
const error = ref('')
/** 错误框「重试」绑定操作：按错误来源设定（默认重载标准，检查失败时重跑检查且保留已选标准） */
const retry = ref<() => void>(() => loadStandards)
/** 左筛选面板：关键字 + 结果 facet（'' = 全部） */
const keyword = ref('')
const filters = ref<Record<string, string>>({})
const detail = ref<StandardCheckResult | null>(null)

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

/** 结果分布取自真实检查结果（后端返回），不造演示数据。 */
const passCount = computed<number>(() => results.value.filter((r) => r.passed).length)
const failCount = computed<number>(() => results.value.length - passCount.value)

/** facet 选项取自契约布尔语义（passed true/false），而非演示数据。 */
const facets = computed<Facet[]>(() => [
  { key: 'passed', label: '结果', options: [
    { v: 'pass', t: '通过' },
    { v: 'fail', t: '未通过' },
  ] },
])

/** 客户端筛选（关键字 + 结果）；数据源为后端检查结果。 */
const filtered = computed<StandardCheckResult[]>(() => {
  const kw = keyword.value.trim().toLowerCase()
  return results.value.filter((r) => {
    const want = filters.value.passed
    if (want === 'pass' && !r.passed) return false
    if (want === 'fail' && r.passed) return false
    if (!kw) return true
    return `${r.code} ${r.engine}`.toLowerCase().includes(kw)
  })
})

/** findings 为契约中的 unknown[]，安全转为可读文本。 */
function findingText(f: unknown): string {
  if (typeof f === 'string') return f
  try {
    return JSON.stringify(f)
  } catch {
    return String(f)
  }
}

function openDetail(r: StandardCheckResult): void {
  detail.value = r
}
function closeDetail(): void {
  detail.value = null
}
/** 顶部/行内「指标目录」入口：跳转既有治理页面（真实路由）。 */
function gotoList(): void {
  router.push('/ind/list')
}

async function init(): Promise<void> {
  try {
    const p = await listProjects()
    projects.value = p.list
    if (routeProjectId.value !== null) selectedProject.value = String(routeProjectId.value)
    if (selectedProject.value) await loadStandards()
  } catch (e) {
    error.value = message(e)
    retry.value = init
  }
}
onMounted(init)

let reqSeq = 0
async function loadStandards(): Promise<void> {
  selectedStd.value = ''
  result.value = null
  results.value = []
  detail.value = null
  if (projectId.value === null) { standards.value = []; return }
  const seq = ++reqSeq
  loading.value = true
  error.value = ''
  try {
    const page = await governanceApi.listStandards(projectId.value)
    if (seq !== reqSeq) return
    standards.value = page.list
  } catch (e) {
    if (seq === reqSeq) {
      error.value = message(e)
      retry.value = loadStandards
    }
  } finally { if (seq === reqSeq) loading.value = false }
}

let runSeq = 0
async function runCheck(): Promise<void> {
  if (projectId.value === null || selectedStd.value === '' || running.value) return
  const seq = ++runSeq
  running.value = true
  error.value = ''
  try {
    const res = await governanceApi.checkStandard(projectId.value, { standardId: Number(selectedStd.value) })
    if (seq !== runSeq) return
    results.value = res
    result.value = res
  } catch (e) {
    if (seq === runSeq) {
      error.value = message(e)
      retry.value = runCheck
    }
  } finally { if (seq === runSeq) running.value = false }
}
</script>

<style scoped>
/* 对标旧版 IndConsistencyView：三卡统计行（检查项数/通过/未通过） */
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px}
.stat-card{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:14px 16px;box-shadow:var(--shadow)}
.stat-num{font-size:22px;font-weight:700}
.stat-label{font-size:11.5px;color:var(--text-3)}
.type-icon{width:34px;height:34px;border-radius:var(--radius);display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;flex-shrink:0}
.finding-list{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:6px;font-size:12px;color:var(--text-2)}
</style>

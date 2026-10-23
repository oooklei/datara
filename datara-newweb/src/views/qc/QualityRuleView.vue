<template>
  <main class="qc-rule-page" aria-label="质量规则">
    <header class="qc-head">
      <div>
        <h1>质量规则</h1>
        <p>按数据资产维护质量规则并执行结构校验；行级结果需绑定数据源，属后续批次。</p>
      </div>
      <label class="qc-project">项目
        <select v-model="selected" data-project-select @change="reload">
          <option value="">请选择项目</option>
          <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
        </select>
      </label>
      <button type="button" data-create :disabled="projectId === null" @click="openCreate">新建规则</button>
    </header>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，执行失败时列表须保留 -->
    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="busy" role="status">正在加载…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="rules.length === 0 && !error" data-empty>暂无质量规则</p>

    <table v-else-if="rules.length > 0" data-rule-list>
      <thead>
        <tr><th>名称</th><th>资产</th><th>表达式</th><th>严重级</th><th>状态</th><th>更新时间</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="rule in rules" :key="rule.id" :data-rule-id="rule.id">
          <td>{{ rule.name }}</td>
          <td data-asset>#{{ rule.assetId }}</td>
          <td data-expr>{{ rule.expression }}</td>
          <td :data-severity="rule.severity">{{ severityLabel(rule.severity) }}</td>
          <td>{{ rule.enabled ? '启用' : '停用' }}</td>
          <td>{{ rule.updatedAt || rule.createdAt || '—' }}</td>
          <td class="actions">
            <button type="button" data-run :disabled="running === rule.id" @click="run(rule)">
              {{ running === rule.id ? '执行中…' : '执行' }}
            </button>
            <button type="button" data-goto-runs @click="gotoRuns">运行记录</button>
          </td>
        </tr>
      </tbody>
    </table>

    <p v-if="runMessage" role="status" data-run-result>{{ runMessage }}</p>
    <p class="qc-note" role="note" data-structural-note>
      structural 口径：执行仅做结构谓词校验，行级四字段恒 0；行级采样需绑定数据源。
    </p>

    <div v-if="editing" class="mask" @click.self="closeEditor">
      <form role="dialog" aria-modal="true" aria-label="新建质量规则" @submit.prevent="save">
        <h2>新建质量规则</h2>
        <label>名称<input v-model.trim="draft.name" required maxlength="128" data-name></label>
        <label>资产 ID<input v-model.number="draft.assetId" type="number" min="1" required data-asset-input></label>
        <label>表达式<textarea v-model.trim="draft.expression" required data-expr-input></textarea></label>
        <label>严重级
          <select v-model="draft.severity" data-severity-select>
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="error">error</option>
          </select>
        </label>
        <label class="check"><input v-model="draft.enabled" type="checkbox" data-enabled>启用</label>
        <footer>
          <button type="button" data-cancel @click="closeEditor">取消</button>
          <button type="submit" data-save>保存</button>
        </footer>
      </form>
    </div>
  </main>
</template>

<script setup lang="ts">
/**
 * 质量五项批 A · 质量规则页（IMPL-v4-07，`/qc/rule`）。
 *
 * 契约面：`governanceApi`（quality-rules 列表 / 创建 / 执行）。
 * 项目上下文：`/qc/rule` 为全局模式路由（AppShell 项目模式仅覆盖 `/p/` 前缀），
 *   故项目段从 `route.params.projectId` 或 `route.query.projectId` 承接；
 *   两者皆空时呈现选择器，不渲染空壳。
 *
 * structural 红线（验收 ④）：执行结果只呈现后端 `summary` 与 `status`，
 *   **不**渲染 `checkedRows/successRows/failedRows/skippedRows` 为行级结论——
 *   该四字段在后端恒 0（api.py L1785-1793），行级采样属后续增量。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  QUALITY_STRUCTURAL_ONLY,
  governanceApi,
  type QualityRuleDraft,
  type QualityRuleRecord,
  type QualitySeverity,
} from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const router = useRouter()

const projects = ref<ProjectSummary[]>([])
const selected = ref('')
const rules = ref<QualityRuleRecord[]>([])
const busy = ref(false)
const error = ref('')
const runMessage = ref('')
const running = ref<number | null>(null)
const editing = ref(false)

const draft = reactive<QualityRuleDraft>({
  assetId: 0,
  name: '',
  expression: '',
  severity: 'warning',
  enabled: true,
})

/** 项目上下文：route 参数优先，其次 query（「运行记录」跨页携带），最后选择器。 */
const routeProjectId = computed<number | null>(() => {
  const raw = route.params.projectId ?? route.query.projectId
  const value = Array.isArray(raw) ? raw[0] : raw
  const n = Number(value)
  return value !== undefined && value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const projectId = computed<number | null>(() => {
  const fromRoute = routeProjectId.value
  if (fromRoute !== null) return fromRoute
  const n = Number(selected.value)
  return selected.value !== '' && Number.isInteger(n) && n > 0 ? n : null
})

const SEVERITY_LABEL: Record<QualitySeverity, string> = { info: '提示', warning: '警告', error: '错误' }
const severityLabel = (s: QualitySeverity): string => SEVERITY_LABEL[s] ?? s
const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

async function loadProjects(): Promise<void> {
  try {
    const page = await listProjects()
    projects.value = page.list
  } catch (e) {
    error.value = message(e)
  }
}

async function reload(): Promise<void> {
  if (projectId.value === null) {
    rules.value = []
    return
  }
  busy.value = true
  error.value = ''
  try {
    const page = await governanceApi.listRules(projectId.value)
    rules.value = page.list
  } catch (e) {
    error.value = message(e)
  } finally {
    busy.value = false
  }
}

function openCreate(): void {
  Object.assign(draft, { assetId: 0, name: '', expression: '', severity: 'warning', enabled: true })
  editing.value = true
}

function closeEditor(): void {
  editing.value = false
}

async function save(): Promise<void> {
  if (projectId.value === null) return
  error.value = ''
  try {
    await governanceApi.createRule(projectId.value, { ...draft })
    editing.value = false
    await reload()
  } catch (e) {
    error.value = message(e)
  }
}

/** 执行规则：只回显后端 structural 口径的 status/summary，不渲染行级结论。 */
async function run(rule: QualityRuleRecord): Promise<void> {
  if (projectId.value === null) return
  running.value = rule.id
  error.value = ''
  runMessage.value = ''
  let failure = ''
  try {
    const result = await governanceApi.runRule(projectId.value, rule.id)
    const issues = result.summary.issues.length ? `；命中禁用词：${result.summary.issues.join('、')}` : ''
    runMessage.value = `规则「${rule.name}」执行完成：${result.status}；${result.summary.message}${issues}（${QUALITY_STRUCTURAL_ONLY.engine} 引擎，行级四字段恒 0）`
  } catch (e) {
    failure = message(e)
  } finally {
    running.value = null
    await reload()
    // reload 会先清空 error，执行失败信息须在其后回写，否则被列表刷新抹掉
    if (failure !== '') error.value = failure
  }
}

function gotoRuns(): void {
  const target = projectId.value
  router.push(target === null ? '/qc/task' : { path: '/qc/task', query: { projectId: String(target) } })
}

onMounted(async () => {
  if (routeProjectId.value !== null) selected.value = String(routeProjectId.value)
  await loadProjects()
  await reload()
})
</script>

<style scoped>
.qc-rule-page{max-width:1180px;margin:auto;padding:32px 24px;color:#172033}
.qc-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.qc-head h1{margin:0}
.qc-head p{margin:4px 0 0;color:#64748b;flex-basis:100%}
.qc-project{display:flex;align-items:center;gap:8px;margin-left:auto}
.qc-project select{padding:7px 10px;min-width:180px}
button{cursor:pointer;padding:7px 12px}
button:disabled{cursor:not-allowed;opacity:.5}
table{width:100%;border-collapse:collapse;background:#fff;margin-top:8px}
th,td{text-align:left;padding:11px;border-bottom:1px solid #e2e8f0;vertical-align:top}
.actions{display:flex;gap:6px}
.qc-note{margin-top:16px;color:#475569;font-size:13px}
.mask{position:fixed;inset:0;background:#0f172a66;display:grid;place-items:center}
.mask form{width:min(520px,calc(100vw - 40px));display:grid;gap:12px;background:#fff;padding:24px;border-radius:10px}
.mask label{display:grid;gap:5px}
.mask input,.mask textarea,.mask select{padding:8px}
.mask textarea{min-height:88px;resize:vertical}
.mask .check{display:flex;align-items:center;gap:8px}
.mask footer{display:flex;justify-content:flex-end;gap:8px}
</style>

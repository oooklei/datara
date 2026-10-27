<template>
  <main class="pg" aria-label="质量规则">
    <header class="pg-head">
      <h1 class="sec-head">质量规则</h1>
      <p class="pg-desc">按数据资产维护质量规则并执行结构校验；行级结果需绑定数据源，属后续批次。</p>
    </header>

    <div class="toolbar">
      <button type="button" class="tb-new" data-create :disabled="projectId === null || saving" @click="openCreate">新建规则</button>
      <span class="spacer"></span>
      <span v-if="projectId !== null" class="hint">共 {{ total }} 条</span>
    </div>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，执行失败时列表须保留 -->
    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="busy || saving" @click="reload">重试</button>
    </div>

    <div v-if="busy" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:34%"></div>
      <div class="skeleton sk-row" style="width:74%"></div>
      <div class="skeleton sk-row" style="width:58%"></div>
    </div>

    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">在上方下拉框选择项目后，即可加载质量规则。</div>
    </div>

    <!-- 空态须让位于错误态：加载失败时不得呈现「暂无数据」空壳 -->
    <div v-else-if="rules.length === 0 && !error" class="panel empty" data-empty>
      <div class="e-title">暂无质量规则</div>
      <div class="e-hint">当前项目下还没有质量规则，点击「新建规则」创建。</div>
    </div>

    <div v-else-if="rules.length > 0" class="panel">
      <div class="tbl-toolbar">
        <span class="sec-head">质量规则</span>
        <span class="pill info">{{ rules.length }}</span>
        <span class="spacer"></span>
        <button type="button" class="op-btn" data-goto-runs @click="gotoRuns">运行记录</button>
      </div>
      <table class="tbl" data-rule-list>
        <thead>
          <tr><th>名称</th><th>资产</th><th>表达式</th><th>严重级</th><th>状态</th><th>更新时间</th><th style="width:140px">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="rule in rules" :key="rule.id" :data-rule-id="rule.id">
            <td>{{ rule.name }}</td>
            <td data-asset><span class="code-chip">#{{ rule.assetId }}</span></td>
            <td data-expr><span class="code-chip">{{ rule.expression }}</span></td>
            <td><span class="pill" :class="severityClass(rule.severity)" :data-severity="rule.severity">{{ severityLabel(rule.severity) }}</span></td>
            <td><span class="st" :class="rule.enabled ? 'st-green' : 'st-gray'"><span class="dot"></span>{{ rule.enabled ? '启用' : '停用' }}</span></td>
            <td>{{ rule.updatedAt || rule.createdAt || '—' }}</td>
            <td class="actions">
              <button type="button" class="op-btn" data-run :disabled="running === rule.id" @click="run(rule)">
                {{ running === rule.id ? '执行中…' : '执行' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-if="runMessage" class="result-line" role="status" data-run-result>{{ runMessage }}</p>
    <p v-if="projectId !== null" class="lock-tip" role="note" data-structural-note>
      structural 口径：执行仅做结构谓词校验，行级四字段恒 0；行级采样需绑定数据源。
    </p>

    <div v-if="editing" class="mask" @click.self="closeEditor">
      <form class="dlg" role="dialog" aria-modal="true" aria-label="新建质量规则" @submit.prevent="save">
        <div class="dlg-hd">新建质量规则<button type="button" class="x" aria-label="关闭" @click="closeEditor">×</button></div>
        <div class="dlg-bd">
          <div class="form-grid">
            <label class="f-item"><span>名称</span><input v-model.trim="draft.name" required maxlength="128" data-name :disabled="saving"></label>
            <label class="f-item"><span>资产 ID</span><input v-model.number="draft.assetId" type="number" min="1" required data-asset-input :disabled="saving"></label>
            <label class="f-item full"><span>表达式</span><textarea v-model.trim="draft.expression" required data-expr-input :disabled="saving"></textarea></label>
            <label class="f-item"><span>严重级</span>
              <select v-model="draft.severity" data-severity-select :disabled="saving">
                <option value="info">info</option>
                <option value="warning">warning</option>
                <option value="error">error</option>
              </select>
            </label>
            <label class="field"><span>启用</span><input v-model="draft.enabled" type="checkbox" data-enabled :disabled="saving"></label>
          </div>
        </div>
        <div class="dlg-ft">
          <button type="button" class="op-btn" data-cancel :disabled="saving" @click="closeEditor">取消</button>
          <button type="submit" class="tb-new" data-save :disabled="saving || draft.name === '' || draft.assetId < 1 || draft.expression === ''">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
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
 *
 * 样式范式：复用全局设计系统（`.pg`/`.panel`/`.tbl`/`.pill`/`.op-btn`/`.tb-new`
 *   + `var(--*)` 令牌），与旧前端 datara-web QcRuleView 的
 *   `.page` + `.card.page-head` + `.card.panel` + `.tbl-toolbar` + `table.tbl` 范式对齐。
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
const total = ref(0)
const busy = ref(false)
const saving = ref(false)
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
const SEVERITY_CLASS: Record<QualitySeverity, string> = { info: 'info', warning: 'warn', error: 'err' }
const severityClass = (s: QualitySeverity): string => SEVERITY_CLASS[s] ?? 'info'
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
    total.value = 0
    return
  }
  busy.value = true
  error.value = ''
  try {
    const page = await governanceApi.listRules(projectId.value)
    rules.value = page.list
    total.value = page.total
  } catch (e) {
    error.value = message(e)
  } finally {
    busy.value = false
  }
}

function openCreate(): void {
  saving.value = false
  Object.assign(draft, { assetId: 0, name: '', expression: '', severity: 'warning', enabled: true })
  editing.value = true
}

function closeEditor(): void {
  editing.value = false
}

async function save(): Promise<void> {
  if (projectId.value === null || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await governanceApi.createRule(projectId.value, { ...draft })
    editing.value = false
    await reload()
  } catch (e) {
    error.value = message(e)
  } finally {
    saving.value = false
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
.actions{display:flex;gap:6px}
</style>

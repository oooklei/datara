<template>
  <div data-ai-root class="ai-root">
    <button
      data-ai-fab
      :aria-expanded="open"
      :aria-label="open ? '关闭 AI 助手' : '打开 AI 助手'"
      class="ai-fab"
      @click="toggleOpen"
    >
      <span class="ai-fab-icon">AI</span>
    </button>

    <aside
      v-if="open"
      data-ai-panel
      class="ai-panel"
      aria-label="AI 助手面板"
    >
      <header class="ai-head">
        <h2>AI 助手</h2>
        <div data-ai-context v-if="pageContext" class="ai-context">
          <span class="ai-context-label">页面</span>
          <span class="ai-context-value">{{ pageContext }}</span>
        </div>
        <button data-ai-close class="ai-close" aria-label="关闭" @click="toggleOpen">×</button>
      </header>

      <section class="ai-tools">
        <h3>八工具</h3>
        <ul class="ai-tool-list">
          <li
            v-for="tool in R8A_TOOLS"
            :key="tool"
            :data-tool="tool"
            :data-tool-enabled="isToolEnabled(tool) ? 'yes' : 'no'"
            :data-tool-active="activeTool === tool ? 'yes' : 'no'"
            class="ai-tool-item"
          >
            <button
              class="ai-tool-btn"
              :disabled="!isToolEnabled(tool)"
              @click="selectTool(tool)"
            >
              <span class="ai-tool-name">{{ TOOL_LABELS[tool] }}</span>
              <span v-if="!isToolEnabled(tool)" class="ai-tool-badge">候 FV-02</span>
            </button>
          </li>
        </ul>
      </section>

      <section v-if="activeTool !== null" class="ai-invoke">
        <h3>{{ TOOL_LABELS[activeTool] }}</h3>

        <!-- run_sql 活接线 -->
        <div v-if="activeTool === 'run_sql'" class="ai-param">
          <label class="ai-field"><span>SQL 语句</span>
            <textarea data-ai-sql-input v-model="sqlInput" rows="5" placeholder="SELECT * FROM ..."></textarea>
          </label>
          <label class="ai-field"><span>数据源 ID</span>
            <input data-ai-datasource-id type="number" min="1" v-model.number="datasourceId" />
          </label>
          <label class="ai-field"><span>数据库</span>
            <input data-ai-database v-model="database" placeholder="可选" />
          </label>
        </div>

        <!-- 七工具占位 -->
        <p v-else class="ai-not-wired" data-not-wired>
          {{ TOOL_LABELS[activeTool] }} 后端 P1-3 桥接未完成，候 FV-02 端到端接入。
        </p>

        <button
          data-ai-run
          :disabled="!canRun || busy !== null"
          class="ai-run-btn"
          @click="runActiveTool"
        >
          {{ busy ? '调用中…' : '调用工具' }}
        </button>
      </section>

      <section v-if="result !== null || errorMsg !== null" class="ai-result">
        <h3>结果</h3>
        <p v-if="errorMsg" class="ai-error" data-ai-error>{{ errorMsg }}</p>
        <pre v-if="result !== null" data-ai-result class="ai-result-pre">{{ formatResult }}</pre>
      </section>
    </aside>
  </div>
</template>

<script setup lang="ts">
/**
 * AI 悬浮助手面板（增量 18 / 票 R8-A 八工具 UI 接线）。
 *
 * 设计约束（权威设计 §4.5 / R8-A 契约 v1）：
 *  - 八工具契约已 GREEN 全量接线（aiToolsApi.ts createAiToolsContract()）；
 *  - 仅 run_sql 活接线（后端 /api/v1/rebuild/ai/tool-calls 已接）；
 *  - 其余七工具标记 NOT_WIRED，候 FV-02 端到端接入；
 *  - 挂载点 AppShell #ai-assistant-global-mount，单实例；
 *  - 全局消费：createAiToolsContract() → invoke() 统一信封调用。
 *
 * 纪律：
 *  - 契约层零裸 fetch；
 *  - 参数校验前置（run_sql 空 SQL 禁发）；
 *  - 信封 ERROR → 呈现错误态，不吞。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { createAiToolsContract, R8A_TOOLS, type R8ATool, type R8AToolsContract } from '../services/rebuild/aiToolsApi'

const props = defineProps<{
  /** AppShell aiContext：当前路由 fullPath，用于页面上下文徽标 */
  pageContext?: string | null
  /** 生产缺省 true；测试注入假契约 */
  contractOverride?: R8AToolsContract
}>()

const contract = props.contractOverride ?? createAiToolsContract()

// ---------- 活工具白名单（仅 run_sql 当前后端已接，其余候 FV-02） ----------
const LIVE_TOOLS: ReadonlySet<R8ATool> = new Set<R8ATool>(['run_sql'])

function isToolEnabled(tool: R8ATool): boolean {
  return LIVE_TOOLS.has(tool)
}

const TOOL_LABELS: Record<R8ATool, string> = {
  search_schema: '搜索 Schema',
  validate_sql: 'SQL 校验',
  run_sql: '执行 SQL',
  get_workflow: '获取工作流',
  validate_workflow: '校验工作流',
  inspect_workflow_run: '检查运行实例',
  get_task_metrics: '任务指标',
  get_lineage: '血缘查询',
}

// ---------- 面板状态 ----------
const open = ref(false)
const activeTool = ref<R8ATool | null>(null)
const busy = ref<'invoke' | null>(null)
const result = ref<unknown>(null)
const errorMsg = ref<string | null>(null)

// ---------- run_sql 参数 ----------
const sqlInput = ref('')
const datasourceId = ref(1)
const database = ref('')

function toggleOpen(): void {
  open.value = !open.value
}

function selectTool(tool: R8ATool): void {
  if (!isToolEnabled(tool)) return
  activeTool.value = tool
  result.value = null
  errorMsg.value = null
}

const canRun = computed(() => {
  if (activeTool.value === null) return false
  if (!isToolEnabled(activeTool.value)) return false
  if (activeTool.value === 'run_sql') {
    return sqlInput.value.trim() !== '' && datasourceId.value > 0
  }
  return true
})

const formatResult = computed(() => {
  if (result.value === null) return ''
  try { return JSON.stringify(result.value, null, 2) } catch { return String(result.value) }
})

async function runActiveTool(): Promise<void> {
  if (!canRun.value || busy.value !== null || activeTool.value === null) return
  busy.value = 'invoke'
  result.value = null
  errorMsg.value = null
  try {
    const params: Record<string, unknown> = { sql: sqlInput.value.trim(), datasourceId: datasourceId.value }
    if (database.value.trim()) params.database = database.value.trim()
    const outcome = await contract.runSql(params, null)
    result.value = outcome
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    errorMsg.value = `工具调用失败：${msg}`
  } finally {
    busy.value = null
  }
}

watch(open, (v) => { if (!v) { activeTool.value = null; result.value = null; errorMsg.value = null } })

onMounted(() => { /* 挂载即显 FAB，等待用户点击 */ })
</script>

<style scoped>
.ai-root{position:fixed;right:20px;bottom:20px;z-index:9999;font-size:13px}
.ai-fab{width:48px;height:48px;border-radius:50%;background:#2563eb;color:#fff;border:none;box-shadow:0 4px 12px rgba(37,99,235,.35);cursor:pointer;display:flex;align-items:center;justify-content:center;font-weight:700}
.ai-fab:hover{background:#1d4ed8}
.ai-fab-icon{font-size:14px;letter-spacing:.5px}
.ai-panel{position:fixed;right:20px;bottom:76px;width:380px;max-height:calc(100vh - 110px);overflow-y:auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px;box-shadow:0 10px 32px rgba(15,23,42,.15);display:flex;flex-direction:column;gap:14px;padding:16px}
.ai-head{display:flex;align-items:center;gap:8px;border-bottom:1px solid #f1f5f9;padding-bottom:10px}
.ai-head h2{margin:0;font-size:15px;font-weight:600}
.ai-close{margin-left:auto;background:none;border:none;font-size:20px;cursor:pointer;color:#64748b;line-height:1}
.ai-context{display:flex;gap:6px;align-items:center;font-size:11px;color:#64748b;background:#f1f5f9;padding:3px 8px;border-radius:10px}
.ai-context-label{color:#94a3b8}
.ai-context-value{max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ai-tools h3,.ai-invoke h3,.ai-result h3{margin:0 0 8px;font-size:13px;font-weight:600;color:#334155}
.ai-tool-list{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(2,1fr);gap:6px}
.ai-tool-btn{display:flex;align-items:center;justify-content:space-between;gap:4px;width:100%;padding:7px 10px;border:1px solid #e2e8f0;border-radius:6px;background:#f8fafc;color:#334155;font-size:12.5px;cursor:pointer}
.ai-tool-btn:hover:not(:disabled){background:#f1f5f9;border-color:#cbd5e1}
.ai-tool-btn:disabled{color:#94a3b8;cursor:not-allowed;background:#f8fafc}
.ai-tool-btn[data-tool-active="yes"]{border-color:#2563eb;background:#eff6ff;color:#1d4ed8}
.ai-tool-badge{font-size:10px;color:#94a3b8;background:#f1f5f9;padding:1px 5px;border-radius:8px}
.ai-invoke{display:flex;flex-direction:column;gap:8px}
.ai-param{display:flex;flex-direction:column;gap:8px}
.ai-field{display:flex;flex-direction:column;gap:4px;font-size:12.5px;color:#475569}
.ai-field textarea,.ai-field input{padding:6px 8px;border:1px solid #cbd5e1;border-radius:6px;font-size:12.5px;color:#172033;background:#fff}
.ai-field textarea{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;resize:vertical;min-height:70px}
.ai-not-wired{color:#92400e;background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:8px 10px;font-size:12.5px;margin:0}
.ai-run-btn{padding:8px 14px;background:#2563eb;color:#fff;border:none;border-radius:6px;font-size:13px;cursor:pointer;align-self:flex-start}
.ai-run-btn:hover:not(:disabled){background:#1d4ed8}
.ai-run-btn:disabled{background:#94a3b8;cursor:not-allowed}
.ai-result{border-top:1px solid #f1f5f9;padding-top:10px}
.ai-error{color:#b91c1c;background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:8px 10px;font-size:12.5px;margin:0}
.ai-result-pre{margin:0;background:#0f172a;color:#e2e8f0;padding:10px;border-radius:6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;max-height:280px;overflow:auto;white-space:pre-wrap;word-break:break-all}
</style>

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
      ref="aiPanelRef"
      data-ai-panel
      class="ai-panel"
      aria-label="AI 助手面板"
      :style="aiPanelStyle"
    >
      <header ref="aiHeadRef" class="ai-head" @pointerdown="onAiDragStart">
        <h2>AI 助手</h2>
        <div data-ai-context v-if="pageContext" class="ai-context">
          <span class="ai-context-label">页面</span>
          <span class="ai-context-value">{{ pageContext }}</span>
        </div>
        <button data-ai-close class="ai-close" aria-label="关闭" @click="toggleOpen">×</button>
      </header>

      <section class="ai-chat">
        <h3>对话</h3>
        <div data-ai-chat-transcript class="ai-chat-transcript" aria-live="polite">
          <p v-if="chatTranscript.length === 0" class="ai-chat-empty">用自然语言查询元数据、SQL、工作流、运行指标或血缘。</p>
          <div v-for="(entry, index) in chatTranscript" :key="index" :class="['ai-chat-message', `is-${entry.role}`]">
            <strong>{{ entry.label }}</strong><span>{{ entry.content }}</span>
          </div>
        </div>
        <label v-if="!projectId" class="ai-field"><span>项目 ID</span>
          <input data-ai-chat-project-id type="number" min="1" v-model.number="chatProjectId" />
        </label>
        <label class="ai-field"><span>问题</span>
          <textarea data-ai-chat-input v-model="chatInput" rows="3" placeholder="例如：检查当前项目最近失败的工作流"></textarea>
        </label>
        <button data-ai-chat-send class="ai-run-btn" :disabled="!canSendChat || chatBusy" @click="sendChat">
          {{ chatBusy ? '分析中…' : '发送' }}
        </button>
      </section>

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
              <span v-if="!isToolEnabled(tool)" class="ai-tool-badge">不可用</span>
            </button>
          </li>
        </ul>
      </section>

      <section v-if="activeTool !== null" class="ai-invoke">
        <h3>{{ TOOL_LABELS[activeTool] }}</h3>

        <!-- run_sql 专用表单 -->
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

        <!-- 其余七工具遵循冻结契约，以可编辑 JSON 承载完整参数面。 -->
        <label v-else class="ai-field"><span>工具参数（JSON）</span>
          <textarea
            data-ai-json-input
            v-model="jsonInput"
            rows="8"
            :placeholder="TOOL_PARAM_TEMPLATES[activeTool]"
          ></textarea>
        </label>

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
 *  - 八工具启停以服务端注册表为准，禁止前端静态白名单漂移；
 *  - run_sql 使用专用表单，其余七工具使用契约 JSON 参数面；
 *  - 挂载点 AppShell #ai-assistant-global-mount，单实例；
 *  - 全局消费：createAiToolsContract() → invoke() 统一信封调用。
 *
 * 纪律：
 *  - 契约层零裸 fetch；
 *  - 参数校验前置（run_sql 空 SQL 禁发）；
 *  - 信封 ERROR → 呈现错误态，不吞。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useDraggable } from '../composables/useDraggable'
import { createAiToolsContract, R8A_TOOLS, type R8ATool, type R8AToolsContract } from '../services/rebuild/aiToolsApi'
import { createAiAgentContract, type AiAgentContract, type AiAgentMessage } from '../services/rebuild/aiAgentApi'

const props = defineProps<{
  /** AppShell aiContext：当前路由 fullPath，用于页面上下文徽标 */
  pageContext?: string | null
  projectId?: number | null
  /** 生产缺省 true；测试注入假契约 */
  contractOverride?: R8AToolsContract
  agentOverride?: AiAgentContract
}>()

const contract = props.contractOverride ?? createAiToolsContract()
const agent = props.agentOverride ?? createAiAgentContract()

// 发现响应到达前仅保留已长期在线的 run_sql；随后完全服从服务端注册表。
const enabledTools = ref<ReadonlySet<R8ATool>>(new Set<R8ATool>(['run_sql']))

function isToolEnabled(tool: R8ATool): boolean {
  return enabledTools.value.has(tool)
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

/* G14 §2.2：AI 浮动窗与弹窗同一拖拽规则（把手=头部）；定位后撤销 right/bottom
 * 锚点，避免 top+bottom 双约束把面板拉伸为满高。 */
const aiPanelRef = ref<HTMLElement | null>(null)
const aiHeadRef = ref<HTMLElement | null>(null)
const { dragStyle: aiRawDragStyle, onHandlePointerdown: onAiDragStart } = useDraggable(aiPanelRef, aiHeadRef, { storageKey: 'ai.panel' })
const aiPanelStyle = computed(() => (aiRawDragStyle.value.position
  ? { ...aiRawDragStyle.value, right: 'auto', bottom: 'auto' }
  : {}))

const activeTool = ref<R8ATool | null>(null)
const busy = ref<'invoke' | null>(null)
const result = ref<unknown>(null)
const errorMsg = ref<string | null>(null)
const chatInput = ref('')
const chatProjectId = ref(props.projectId ?? 0)
const chatBusy = ref(false)
const agentMessages = ref<AiAgentMessage[]>([])
const chatTranscript = ref<Array<{ role: 'user' | 'assistant' | 'tool'; label: string; content: string }>>([])

// ---------- run_sql 参数 ----------
const sqlInput = ref('')
const datasourceId = ref(1)
const database = ref('')
const jsonInput = ref('')

const TOOL_PARAM_TEMPLATES: Record<R8ATool, string> = {
  search_schema: '{"project_id": 1, "keyword": "orders", "include_columns": true}',
  validate_sql: '{"project_id": 1, "datasource_id": 1, "sql": "SELECT 1"}',
  run_sql: '',
  get_workflow: '{"project_id": 1, "workflow_id": 1}',
  validate_workflow: '{"project_id": 1, "workflow_id": 1}',
  inspect_workflow_run: '{"project_id": 1, "run_id": "run-id", "include_tasks": true}',
  get_task_metrics: '{"project_id": 1, "run_id": "run-id", "group_by": "status"}',
  get_lineage: '{"project_id": 1, "entity_type": "TABLE", "entity": "schema.table", "direction": "BOTH", "depth": 3}',
}

const canSendChat = computed(() => chatProjectId.value > 0 && chatInput.value.trim() !== '')

function toggleOpen(): void {
  open.value = !open.value
}

function selectTool(tool: R8ATool): void {
  if (!isToolEnabled(tool)) return
  activeTool.value = tool
  jsonInput.value = tool === 'run_sql' ? '' : TOOL_PARAM_TEMPLATES[tool]
  result.value = null
  errorMsg.value = null
}

const canRun = computed(() => {
  if (activeTool.value === null) return false
  if (!isToolEnabled(activeTool.value)) return false
  if (activeTool.value === 'run_sql') {
    return sqlInput.value.trim() !== '' && datasourceId.value > 0
  }
  try {
    const parsed = JSON.parse(jsonInput.value)
    return parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
  } catch {
    return false
  }
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
    let params: Record<string, unknown>
    if (activeTool.value === 'run_sql') {
      params = { sql: sqlInput.value.trim(), datasourceId: datasourceId.value }
      if (database.value.trim()) params.database = database.value.trim()
    } else {
      params = JSON.parse(jsonInput.value) as Record<string, unknown>
    }
    const outcome = await invokeTool(activeTool.value, params)
    result.value = outcome
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    errorMsg.value = `工具调用失败：${msg}`
  } finally {
    busy.value = null
  }
}

function invokeTool(tool: R8ATool, params: Record<string, unknown>): Promise<unknown> {
  switch (tool) {
    case 'search_schema': return contract.searchSchema(params, null)
    case 'validate_sql': return contract.validateSql(params, null)
    case 'run_sql': return contract.runSql(params, null)
    case 'get_workflow': return contract.getWorkflow(params, null)
    case 'validate_workflow': return contract.validateWorkflow(params, null)
    case 'inspect_workflow_run': return contract.inspectWorkflowRun(params, null)
    case 'get_task_metrics': return contract.getTaskMetrics(params, null)
    case 'get_lineage': return contract.getLineage(params, null)
  }
}

async function sendChat(): Promise<void> {
  if (!canSendChat.value || chatBusy.value) return
  const question = chatInput.value.trim()
  chatInput.value = ''
  chatBusy.value = true
  errorMsg.value = null
  agentMessages.value.push({ role: 'user', content: question })
  chatTranscript.value.push({ role: 'user', label: '你', content: question })
  try {
    for (let step = 0; step < 4; step += 1) {
      const turn = await agent.complete(chatProjectId.value, agentMessages.value)
      agentMessages.value.push(turn.message)
      const calls = turn.message.toolCalls ?? []
      if (calls.length === 0) {
        const answer = turn.message.content?.trim() || '模型未返回可展示内容。'
        chatTranscript.value.push({ role: 'assistant', label: 'AI', content: answer })
        return
      }
      if (calls.length > 8) throw new Error('单轮工具调用超过 8 个安全上限')
      for (const call of calls) {
        if (!R8A_TOOLS.includes(call.function.name as R8ATool)) {
          throw new Error(`模型请求了未登记工具：${call.function.name}`)
        }
        let params: Record<string, unknown>
        try {
          const parsed = JSON.parse(call.function.arguments)
          if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('arguments must be object')
          params = parsed as Record<string, unknown>
        } catch {
          throw new Error(`工具参数不是有效 JSON：${call.function.name}`)
        }
        // 项目主权只取当前受信页面/用户输入，绝不采信模型给出的跨项目 id。
        params.project_id = chatProjectId.value
        chatTranscript.value.push({ role: 'tool', label: '工具', content: `调用 ${call.function.name}` })
        let toolResult: unknown
        try {
          toolResult = await invokeTool(call.function.name as R8ATool, params)
        } catch (err) {
          toolResult = { error: err instanceof Error ? err.message : String(err) }
        }
        const serialized = JSON.stringify(toolResult)
        agentMessages.value.push({
          role: 'tool',
          toolCallId: call.id,
          content: serialized.length > 16_000 ? `${serialized.slice(0, 16_000)}…` : serialized,
        })
      }
    }
    throw new Error('Agent 工具调用超过 4 轮安全上限')
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    errorMsg.value = `AI 对话失败：${msg}`
  } finally {
    chatBusy.value = false
  }
}

watch(open, (v) => { if (!v) { activeTool.value = null; result.value = null; errorMsg.value = null } })
watch(() => props.projectId, (value) => { if (value) chatProjectId.value = value })

onMounted(async () => {
  try {
    const registry = await contract.discoverRegistry()
    enabledTools.value = new Set(
      registry
        .filter((entry) => entry.enabled && R8A_TOOLS.includes(entry.name as R8ATool))
        .map((entry) => entry.name as R8ATool),
    )
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    errorMsg.value = `工具注册表加载失败：${msg}`
  }
})
</script>

<style scoped>
.ai-root{position:fixed;right:20px;bottom:20px;z-index:9999;font-size:13px}
.ai-fab{width:48px;height:48px;border-radius:50%;background:var(--primary);color:var(--card);border:none;box-shadow:var(--shadow-primary);cursor:pointer;display:flex;align-items:center;justify-content:center;font-weight:700}
.ai-fab:hover{background:var(--primary-hover)}
.ai-fab-icon{font-size:14px;letter-spacing:.5px}
/* 375 档：min() 收口宽度，杜绝 380px 固定宽横向失控 */
.ai-panel{position:fixed;right:20px;bottom:76px;width:min(380px,calc(100vw - 32px));max-height:calc(100vh - 110px);overflow-y:auto;background:var(--card);border:1px solid var(--border);border-radius:12px;box-shadow:var(--shadow-xl);display:flex;flex-direction:column;gap:14px;padding:16px}
.ai-head{display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border);padding-bottom:10px;cursor:grab;user-select:none}
.ai-head:active{cursor:grabbing}
.ai-head h2{margin:0;font-size:15px;font-weight:600}
.ai-chat{display:flex;flex-direction:column;gap:8px}
.ai-chat h3{margin:0;font-size:13px}
.ai-chat-transcript{max-height:180px;overflow:auto;border:1px solid var(--border);border-radius:8px;padding:8px;background:var(--bg)}
.ai-chat-empty{margin:0;color:var(--text-2)}
.ai-chat-message{display:flex;gap:8px;margin:5px 0;line-height:1.45;white-space:pre-wrap}
.ai-chat-message strong{flex:0 0 32px;color:var(--text-2)}.ai-chat-message.is-tool{font-size:12px;color:var(--primary)}
.ai-close{margin-left:auto;background:none;border:none;font-size:20px;cursor:pointer;color:var(--text-3);line-height:1}
.ai-context{display:flex;gap:6px;align-items:center;font-size:11px;color:var(--text-2);background:var(--bg);padding:3px 8px;border-radius:10px}
.ai-context-label{color:var(--text-3)}
.ai-context-value{max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ai-tools h3,.ai-invoke h3,.ai-result h3{margin:0 0 8px;font-size:13px;font-weight:600;color:var(--text)}
.ai-tool-list{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(2,1fr);gap:6px}
.ai-tool-btn{display:flex;align-items:center;justify-content:space-between;gap:4px;width:100%;padding:7px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:12.5px;cursor:pointer}
.ai-tool-btn:hover:not(:disabled){background:var(--bg-deep);border-color:var(--border-strong)}
.ai-tool-btn:disabled{color:var(--text-3);cursor:not-allowed;background:var(--bg)}
.ai-tool-btn[data-tool-active="yes"]{border-color:var(--primary);background:var(--primary-light);color:var(--primary)}
.ai-tool-badge{font-size:10px;color:var(--text-3);background:var(--bg-deep);padding:1px 5px;border-radius:8px}
.ai-invoke{display:flex;flex-direction:column;gap:8px}
.ai-param{display:flex;flex-direction:column;gap:8px}
.ai-field{display:flex;flex-direction:column;gap:4px;font-size:12.5px;color:var(--text-2)}
.ai-field textarea,.ai-field input{padding:6px 8px;border:1px solid var(--border-strong);border-radius:6px;font-size:12.5px;color:var(--text);background:var(--card)}
.ai-field textarea{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;resize:vertical;min-height:70px}
.ai-not-wired{color:var(--warn);background:var(--warn-bg);border:1px solid var(--warn);border-radius:6px;padding:8px 10px;font-size:12.5px;margin:0}
.ai-run-btn{padding:8px 14px;background:var(--primary);color:var(--card);border:none;border-radius:6px;font-size:13px;cursor:pointer;align-self:flex-start}
.ai-run-btn:hover:not(:disabled){background:var(--primary-hover)}
.ai-run-btn:disabled{background:var(--text-3);cursor:not-allowed}
.ai-result{border-top:1px solid var(--border);padding-top:10px}
.ai-error{color:var(--danger);background:var(--danger-bg);border:1px solid var(--danger);border-radius:6px;padding:8px 10px;font-size:12.5px;margin:0}
/* 代码回显块恒暗底（双主题一致的代码块惯例），色值取侧栏令牌 */
.ai-result-pre{margin:0;background:var(--sidebar-2);color:var(--sidebar-text);padding:10px;border-radius:6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;max-height:280px;overflow:auto;white-space:pre-wrap;word-break:break-all}
</style>

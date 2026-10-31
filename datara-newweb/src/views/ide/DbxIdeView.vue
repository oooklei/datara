<template>
  <main class="dbx-ide-page" aria-label="数据开发IDE">
    <header class="dbx-ide-head">
      <div class="dbx-ide-heading">
        <h1>数据开发 IDE</h1>
        <p class="dbx-ide-context" data-dbx-context>
          项目：<b data-dbx-project>{{ projectLabel }}</b>
          <span class="dbx-ide-sep">·</span>
          环境组：<b data-dbx-environment>{{ selectedEnvironment?.name ?? '未选择' }}</b>
        </p>
      </div>
      <div class="dbx-ide-actions">
        <label class="dbx-env-field">环境组
          <select
            v-model.number="environmentGroupId"
            data-environment-group
            @change="refreshVariables"
          >
            <option :value="null">未选择</option>
            <option v-for="row in environmentOptions" :key="row.id!" :value="row.id!">{{ row.name }}</option>
          </select>
        </label>
        <button v-if="environmentError" type="button" data-environment-retry @click="refreshEnvironments">{{ environmentError }}；重试</button>
        <button type="button" data-variable-refresh :disabled="projectId === null || loading" @click="refreshVariables">
          {{ loading ? '加载中…' : '刷新变量' }}
        </button>
        <button type="button" data-variable-manage :disabled="projectId === null" @click="drawerOpen = true">变量管理</button>
      <button v-if="ideReady" type="button" data-ide-reload @click="retryIde">重载数据开发工具</button>
      </div>
    </header>

    <p v-if="projectId === null" class="dbx-ide-muted" data-no-project>请先选择项目</p>
    <template v-else>
      <div v-if="sessionError || frameError" class="dbx-ide-retry" role="alert" data-ide-session-error>
        <span>数据开发工具加载失败：{{ sessionError || frameError }}</span>
        <button type="button" data-ide-retry @click="retryIde">重试加载</button>
      </div>
      <p v-else-if="!ideReady" class="dbx-ide-muted" data-ide-session-loading>正在准备 IDE 会话…</p>
      <p v-else-if="!frameLoaded" class="dbx-ide-muted" data-ide-frame-loading>正在加载数据开发页面…</p>
      <p v-if="error" class="dbx-ide-error" role="alert" data-variable-error>变量加载失败：{{ error }}</p>
      <section class="dbx-ide-body">
        <iframe
          v-if="ideReady && !frameError"
          :key="frameGeneration"
          id="dbx-ide-frame"
          ref="frameEl"
          class="dbx-ide-frame"
          data-dbx-frame
          src="/ide/"
          title="数据开发 IDE"
          @load="onFrameLoad"
          @error="onFrameError"
        ></iframe>
        <aside class="dbx-var-panel" data-variable-panel aria-label="变量现值">
          <header class="dbx-var-head">
            <h2>变量现值</h2>
            <small>{{ entries.length }} 项</small>
          </header>
          <p v-if="entries.length === 0" class="dbx-ide-muted" data-variable-empty>当前项目暂无可用变量</p>
          <ul v-else class="dbx-var-list">
            <li v-for="item in entries" :key="`${item.scope}.${item.name}`" class="dbx-var-row" data-variable-row>
              <code class="dbx-var-name">{{ item.scope }}.{{ item.name }}</code>
              <small class="dbx-var-type">{{ item.valueType }}</small>
              <span v-if="item.sensitive" class="dbx-var-value is-masked" data-variable-masked>{{ item.value }}</span>
              <span v-else class="dbx-var-value" data-variable-value>{{ item.value ?? '（不可解析）' }}</span>
            </li>
          </ul>
        </aside>
      </section>
    </template>

    <VariableManagerDrawer
      :model-value="drawerOpen"
      :project-id="projectId ?? undefined"
      @update:model-value="onDrawerToggle"
    />
  </main>
</template>

<script setup lang="ts">
/**
 * dbx IDE 宿主页（`/ide` 与 `/p/:projectId/ide`）。
 *
 * datara 不再自研 IDE：本页仅承载宿主职责——项目/环境组上下文、变量现值面板、
 * 变量管理抽屉入口，以及把变量现值经 `datara:variables` 下发给 iframe（dbx，子路径 `/ide/`）。
 * 项目上下文沿用既有口径：路由注入的 prop 优先，其次 route 参数/query（工作区壳负责项目选择，
 * 本页不含项目选择器）。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { createVariableContract } from '../../services/rebuild/variableApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'
import {
  buildVariableEntries,
  sendVariablesToDbx,
  type ExternalVariableEntry,
} from '../../services/rebuild/dbxVariableBridge'
import VariableManagerDrawer from '../variables/VariableManagerDrawer.vue'
import { authAccount } from '../../services/rebuild/authApi'
import { issueDbxIdeSession } from '../../services/rebuild/dbxIdeApi'
import { sanitizeEmbeddedBranding } from '../../services/rebuild/embeddedBranding'
import { useEnvironmentContext } from '../../services/rebuild/environmentContext'

const props = defineProps<{ projectId?: number }>()
const route = useRoute()

const varApi = createVariableContract()
const frameEl = ref<HTMLIFrameElement | null>(null)
const drawerOpen = ref(false)
const loading = ref(false)
const error = ref('')
const entries = ref<ExternalVariableEntry[]>([])
const projects = ref<ProjectSummary[]>([])
const ideReady = ref(false)
const sessionError = ref('')
const frameError = ref('')
const frameLoaded = ref(false)
const frameGeneration = ref(0)
let sessionGeneration = 0
let variableGeneration = 0
let projectGeneration = 0
let sessionQueue: Promise<void> = Promise.resolve()
let frameTimeout: ReturnType<typeof setTimeout> | undefined
let disposeEmbeddedBranding: (() => void) | undefined

function clearFrameTimeout(): void {
  if (frameTimeout !== undefined) clearTimeout(frameTimeout)
  frameTimeout = undefined
}

function onFrameError(): void {
  clearFrameTimeout()
  frameError.value = '页面请求失败'
}

function onFrameLoad(): void {
  clearFrameTimeout()
  frameLoaded.value = true
  disposeEmbeddedBranding?.()
  try {
    const document = frameEl.value?.contentDocument
    disposeEmbeddedBranding = document ? sanitizeEmbeddedBranding(document) : undefined
  } catch {
    disposeEmbeddedBranding = undefined
  }
}

const routeProjectId = computed<number | null>(() => {
  const raw = route.params.projectId ?? route.query.projectId
  const value = Array.isArray(raw) ? raw[0] : raw
  const n = Number(value)
  return value !== undefined && value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const projectId = computed<number | null>(() => {
  if (Number.isInteger(props.projectId) && props.projectId! > 0) return props.projectId!
  return routeProjectId.value
})
const {
  options: environmentOptions,
  selectedId: environmentGroupId,
  selected: selectedEnvironment,
  error: environmentError,
  refresh: refreshEnvironments,
} = useEnvironmentContext(projectId)
const projectLabel = computed(() => {
  if (projectId.value === null) return '未选择'
  return projects.value.find((p) => p.id === projectId.value)?.name ?? `项目 #${projectId.value}`
})

async function loadProjects(): Promise<void> {
  const generation = ++projectGeneration
  try {
    const rows = (await listProjects()).list
    if (generation === projectGeneration) projects.value = rows
  } catch {
    if (generation === projectGeneration) projects.value = []
  }
}

/** 拉取变量现值并下发；敏感变量在 buildVariableEntries 内即脱敏。 */
async function refreshVariables(): Promise<void> {
  const generation = ++variableGeneration
  const id = projectId.value
  if (id === null) {
    entries.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    const items = await varApi.completeVariables(
      '',
      environmentGroupId.value ? { projectId: id, environmentGroupId: environmentGroupId.value } : { projectId: id },
    )
    if (generation !== variableGeneration) return
    entries.value = buildVariableEntries(items)
  } catch (e) {
    if (generation !== variableGeneration) return
    entries.value = []
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (generation === variableGeneration) loading.value = false
  }
  if (generation !== variableGeneration) return
  sendVariablesToDbx(entries.value)
}

function startIdeSession(id: number | null, account: typeof authAccount.value): void {
  const generation = ++sessionGeneration
  clearFrameTimeout()
  ideReady.value = false
  sessionError.value = ''
  frameError.value = ''
  frameLoaded.value = false
  frameGeneration.value += 1
  error.value = ''
  entries.value = []
  ++variableGeneration
  loading.value = false
  if (id === null || account === null) return
  // Serialize Set-Cookie responses: an old in-flight response cannot overwrite
  // the cookie issued for the newly selected account or project.
  sessionQueue = sessionQueue.then(async () => {
    if (generation !== sessionGeneration) return
    try {
      await issueDbxIdeSession(id)
      if (generation !== sessionGeneration) return
      ideReady.value = true
      frameTimeout = setTimeout(() => {
        if (generation === sessionGeneration && !frameLoaded.value) {
          frameError.value = '页面响应超时，请重试'
        }
      }, 15000)
      void refreshVariables()
    } catch (e) {
      if (generation === sessionGeneration) {
        sessionError.value = e instanceof Error ? e.message : String(e)
      }
    }
  })
}

function retryIde(): void {
  startIdeSession(projectId.value, authAccount.value)
}

watch([projectId, authAccount], ([id, account]) => {
  startIdeSession(id, account)
}, { immediate: true })

watch(authAccount, (account) => {
  ++projectGeneration
  projects.value = []
  if (account !== null) void loadProjects()
}, { immediate: true })

/** dbx 侧就绪后补发一次：覆盖 iframe 晚于宿主拉取完成的时序。 */
function onBridgeReady(event: MessageEvent): void {
  // dbx 用 window.parent.postMessage 发的是 message 事件，而非同名 DOM Event；
  // 必须先按 data.type 过滤，再校验来源是否为当前 iframe。
  const data = event.data as { type?: unknown } | null
  if (!data || typeof data !== 'object' || data.type !== 'datara:bridge-ready') return
  const source = frameEl.value?.contentWindow ?? null
  if (source === null || event.source !== source) return
  clearFrameTimeout()
  frameLoaded.value = true
  frameError.value = ''
  sendVariablesToDbx(entries.value)
}

function onDrawerToggle(open: boolean): void {
  drawerOpen.value = open
  if (!open) void refreshVariables()
}

onMounted(() => {
  window.addEventListener('message', onBridgeReady)
})

onUnmounted(() => {
  clearFrameTimeout()
  ++sessionGeneration
  ++variableGeneration
  ++projectGeneration
  window.removeEventListener('message', onBridgeReady)
  disposeEmbeddedBranding?.()
  disposeEmbeddedBranding = undefined
})
</script>

<style scoped>
.dbx-ide-page{display:flex;flex-direction:column;gap:12px;min-height:100%;padding:16px 20px;color:var(--text);background:var(--bg)}
.dbx-ide-head{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap}
.dbx-ide-heading h1{margin:0;font-size:20px}
.dbx-ide-context{margin:4px 0 0;color:var(--text-2);font-size:13px}
.dbx-ide-context b{color:var(--text);font-weight:600}
.dbx-ide-sep{margin:0 8px;color:var(--text-3)}
.dbx-ide-actions{display:flex;align-items:center;gap:10px;margin-left:auto;flex-wrap:wrap}
.dbx-env-field{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-2)}
.dbx-env-field input{width:96px;padding:5px 8px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--card);color:var(--text);font:inherit}
.dbx-env-field select{min-width:140px;padding:5px 8px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--card);color:var(--text);font:inherit}
.dbx-ide-actions button{padding:5px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--card);color:var(--text);font:inherit;cursor:pointer}
.dbx-ide-actions button:hover:not(:disabled){border-color:var(--primary);color:var(--primary)}
.dbx-ide-actions button:disabled{opacity:.5;cursor:not-allowed}
.dbx-ide-body{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:12px}
.dbx-ide-frame{width:100%;height:calc(100vh - 200px);min-height:480px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card)}
.dbx-var-panel{display:flex;flex-direction:column;gap:8px;padding:12px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card);overflow:auto;max-height:calc(100vh - 200px)}
.dbx-var-head{display:flex;align-items:baseline;justify-content:space-between}
.dbx-var-head h2{margin:0;font-size:14px}
.dbx-var-head small{color:var(--text-2)}
.dbx-var-list{list-style:none;margin:0;padding:0;display:grid;gap:6px}
.dbx-var-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:6px 8px;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:12px}
.dbx-var-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)}
.dbx-var-type{color:var(--text-3);font-size:11px}
.dbx-var-value{color:var(--text-2);max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dbx-var-value.is-masked{color:var(--warn);letter-spacing:1px}
.dbx-ide-muted{margin:0;color:var(--text-2);font-size:13px}
.dbx-ide-error{margin:0;padding:6px 10px;border-radius:var(--radius-sm);background:var(--danger-bg);color:var(--danger);font-size:12px}
.dbx-ide-retry{display:flex;align-items:center;gap:12px;margin:0;padding:6px 10px;border-radius:var(--radius-sm);background:var(--danger-bg);color:var(--danger);font-size:12px}
.dbx-ide-retry button{border:1px solid currentColor;border-radius:var(--radius-sm);background:transparent;color:inherit;padding:4px 10px;cursor:pointer}
@media(max-width:1000px){.dbx-ide-body{grid-template-columns:minmax(0,1fr)}.dbx-var-panel{max-height:260px}.dbx-ide-frame{height:70vh}}
</style>

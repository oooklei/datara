<template>
  <main class="pg" aria-label="API 管理">
    <header class="pg-head">
      <h1 class="sec-head">API 管理</h1>
      <p class="pg-desc">受控 Facade API 定义与状态流转（draft / published / disabled）。调用日志以页内页签呈现，不设独立菜单。</p>
    </header>

    <!-- 权威裁定 C1（增量 15.2 §四）：调用日志为「API 管理」页内页签；
         /open/log 维持 embedded，永不恢复独立一级菜单。 -->
    <div class="hub-tabs" role="tablist" aria-label="API 管理视图">
      <button type="button" class="hub-tab" :class="{ on: tab === 'api' }" role="tab"
              :aria-selected="tab === 'api'" data-tab="api" @click="switchTab('api')">API 列表</button>
      <button type="button" class="hub-tab" :class="{ on: tab === 'log' }" role="tab"
              :aria-selected="tab === 'log'" data-tab="log" @click="switchTab('log')">调用日志</button>
    </div>

    <!-- ================= API 列表页签 ================= -->
    <div v-if="tab === 'api'">
      <div class="toolbar">
        <span class="pill" :class="isNotWired ? 'off' : 'info'" data-wired-state>
          {{ isNotWired ? '后端未接线' : '已接线' }}
        </span>
        <span class="spacer"></span>
        <span class="hint" data-api-count>API {{ items.length }} 条</span>
        <button type="button" class="op-btn" data-refresh :disabled="loading" @click="load">刷新</button>
        <button type="button" class="op-btn" data-goto-key @click="gotoKey">API-Key管理</button>
      </div>

      <div v-if="error" class="err-box" role="alert" data-error>
        <span>{{ error }}</span>
        <button type="button" class="op-btn retry" :disabled="loading" @click="load">重试</button>
      </div>

      <div v-if="loading" class="panel" role="status" aria-live="polite">
        <div class="skeleton sk-row" style="width:34%"></div>
        <div class="skeleton sk-row" style="width:70%"></div>
        <div class="skeleton sk-row" style="width:52%"></div>
      </div>

      <div v-else-if="isNotWired" class="panel empty" data-not-wired>
        <div class="e-title">后端未接线</div>
        <div class="e-hint">{{ notWiredMsg }}</div>
      </div>

      <div v-else-if="items.length === 0" class="panel empty" data-empty>
        <div class="e-title">暂无 API 定义</div>
        <div class="e-hint">后端 15.2-A~D 接线后可在此登记受控 Facade API 定义。</div>
      </div>

      <div v-else class="panel">
        <div class="tbl-toolbar">
          <span class="sec-head">API 列表</span>
          <span class="pill info">{{ items.length }}</span>
          <span class="spacer"></span>
        </div>
        <table class="tbl" data-api-list>
          <thead>
            <tr>
              <th>名称</th><th>方法</th><th>路径</th><th>权限</th><th>状态</th><th>版本</th><th>更新时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in items" :key="a.id" :data-api-id="a.id">
              <td>
                <strong>{{ a.name }}</strong>
                <span class="mono" data-api-path>{{ a.method }} {{ a.path }}</span>
              </td>
              <td><span class="pill" :class="methodClass(a.method)">{{ a.method }}</span></td>
              <td class="mono">{{ a.path }}</td>
              <td class="mono">{{ a.requiredPermission }}</td>
              <td><span class="st" :class="statusClass(a.status)"><span class="dot"></span>{{ a.status }}</span></td>
              <td class="mono">{{ a.version }}</td>
              <td class="mono">{{ a.updatedAt }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ================= 调用日志页签 ================= -->
    <div v-else>
      <div class="toolbar">
        <span class="pill" :class="logsNotWired ? 'off' : 'info'" data-logs-wired-state>
          {{ logsNotWired ? '后端未接线' : '已接线' }}
        </span>
        <span class="spacer"></span>
        <span class="hint" data-logs-count>日志 {{ logs.list.length }} / {{ logs.total }} 条</span>
        <button type="button" class="op-btn" data-logs-refresh :disabled="logsLoading" @click="loadLogs">刷新</button>
      </div>

      <div v-if="logsError" class="err-box" role="alert" data-logs-error>
        <span>{{ logsError }}</span>
        <button type="button" class="op-btn retry" :disabled="logsLoading" @click="loadLogs">重试</button>
      </div>

      <div v-if="logsLoading" class="panel" role="status" aria-live="polite">
        <div class="skeleton sk-row" style="width:44%"></div>
        <div class="skeleton sk-row" style="width:76%"></div>
      </div>

      <div v-else-if="logsNotWired" class="panel empty" data-logs-not-wired>
        <div class="e-title">调用日志后端未接线</div>
        <div class="e-hint">{{ notWiredMsg }}</div>
      </div>

      <div v-else-if="logs.list.length === 0" class="panel empty" data-logs-empty>
        <div class="e-title">暂无调用日志</div>
        <div class="e-hint">网关开始记录调用后，可在此按 API / Key 检索脱敏日志。</div>
      </div>

      <div v-else class="panel">
        <div class="tbl-toolbar">
          <span class="sec-head">调用日志</span>
          <span class="pill info">{{ logs.list.length }} / {{ logs.total }}</span>
          <span class="spacer"></span>
        </div>
        <table class="tbl" data-call-log-list>
          <thead>
            <tr>
              <th>时间</th><th>API</th><th>Key</th><th>主体</th><th>状态码</th><th>结果</th><th>错误码</th><th>耗时</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in logs.list" :key="l.requestId" :data-request-id="l.requestId">
              <td class="mono">{{ l.requestedAt }}</td>
              <td class="mono">{{ l.apiId }}</td>
              <td class="mono">{{ l.keyId }}</td>
              <td>{{ l.principal }}</td>
              <td class="mono">{{ l.statusCode }}</td>
              <td><span class="st" :class="resultClass(l.result)"><span class="dot"></span>{{ l.result }}</span></td>
              <td class="mono">{{ l.errorCode ?? '—' }}</td>
              <td class="mono">{{ l.latencyMs }} ms</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
/**
 * 增量 15.3-A：API 管理页（`/open/api`）。
 *
 * 契约面：`openapiAdminApi`（createOpenapiAdminContract）——
 *   列表 / 状态流转 / 调用日志页签（listCallLogs）。
 * 权威裁定 C1（增量 15.2 §四，2026-10-21 用户批准）：调用日志为**本页内页签**，
 *   `/open/log` 维持 embedded，永不恢复独立一级菜单 → 不新增路由。
 * 互跳：`/open/api` ⇄ `/open/key`（两路由均已在 routes.ts 注册，无死链）。
 *
 * 样式对标旧前端：页面壳 `.pg/.pg-head/.pg-desc/.toolbar/.panel/.tbl-toolbar/.tbl`
 *   与页签 `.hub-tabs/.hub-tab` 全部取自 theme.css 全局令牌层，无 scoped 裸色值。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  createOpenapiAdminContract,
  OPENAPI_ADMIN_NOT_WIRED,
  type ApiCallLogPage,
  type ApiDefinitionRecord,
  type ApiDefinitionStatus,
  type ApiDefinitionMethod,
} from '../../services/rebuild/openapiAdminApi'

const router = useRouter()
const contract = createOpenapiAdminContract()

type TabKey = 'api' | 'log'

const tab = ref<TabKey>('api')
const items = ref<ApiDefinitionRecord[]>([])
const loading = ref(false)
const error = ref('')
const isNotWired = ref(false)
const notWiredMsg = OPENAPI_ADMIN_NOT_WIRED

/* 调用日志页签：延迟到首次切换时加载（避免无谓请求）。 */
const logs = ref<ApiCallLogPage>({ total: 0, list: [] })
const logsLoading = ref(false)
const logsError = ref('')
const logsNotWired = ref(false)
let logsLoaded = false

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))
const isNotWiredError = (e: unknown): boolean => message(e).includes('OPENAPI_ADMIN_NOT_WIRED')

function switchTab(next: TabKey): void {
  tab.value = next
  if (next === 'log' && !logsLoaded) {
    void loadLogs()
  }
}

/** 互跳入口：两页路由均已注册，跳转目标真实可达。 */
function gotoKey(): void {
  router.push('/open/key')
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  isNotWired.value = false
  try {
    items.value = await contract.listApiDefinitions()
  } catch (e) {
    if (isNotWiredError(e)) {
      isNotWired.value = true
    } else {
      error.value = message(e)
    }
  } finally {
    loading.value = false
  }
}

async function loadLogs(): Promise<void> {
  logsLoading.value = true
  logsError.value = ''
  logsNotWired.value = false
  try {
    logs.value = await contract.listCallLogs({ limit: 100 })
    logsLoaded = true
  } catch (e) {
    if (isNotWiredError(e)) {
      logsNotWired.value = true
    } else {
      logsError.value = message(e)
    }
  } finally {
    logsLoading.value = false
  }
}

const methodClass = (m: ApiDefinitionMethod): string => (m === 'GET' ? 'info' : 'purple')
const statusClass = (s: ApiDefinitionStatus): string =>
  s === 'published' ? 'st-green' : s === 'disabled' ? 'st-red' : 'st-gray'
const resultClass = (r: 'success' | 'denied' | 'error'): string =>
  r === 'success' ? 'st-green' : r === 'denied' ? 'st-red' : 'st-orange'

onMounted(load)
</script>

<style scoped>
/* 仅保留全局类无法表达的布局/语义态；颜色一律走令牌 */
.pg > div{display:flex;flex-direction:column;gap:14px}
.mono{font-family:ui-monospace,SFMono-Regular,Consolas,Menlo,monospace;font-size:12px}
td > span{display:block}
td > span.mono{color:var(--text-3);margin-top:2px}
</style>

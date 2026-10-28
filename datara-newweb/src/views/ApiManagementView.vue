<template>
  <main class="pg" aria-label="API 管理">
    <header class="pg-head">
      <div><h1>API 管理</h1><p>登记受控 Datara Facade，并查看脱敏调用日志。</p></div>
      <a class="op-btn" href="/open/key" data-goto-key>API-Key 管理</a>
    </header>
    <nav class="tabs" aria-label="API 管理视图">
      <button type="button" :class="{ active: tab === 'definitions' }" data-tab="api" @click="tab = 'definitions'">API 定义</button>
      <button type="button" :class="{ active: tab === 'logs' }" data-tab="log" @click="tab = 'logs'">调用日志</button>
    </nav>
    <section v-if="tab === 'definitions'">
      <div class="toolbar"><input v-model.trim="definitionKeyword" data-filter-keyword placeholder="搜索名称或路径"><span class="hint" data-api-count>API {{ filteredItems.length }} 条</span><span class="spacer"></span><button type="button" data-refresh :disabled="busy" @click="load">刷新</button><button type="button" class="primary" data-create :disabled="mutationBusy" @click="openCreate">+ 新建 API</button></div>
      <p v-if="error" class="err-box" role="alert" data-error>{{ error }}</p><p v-if="busy" role="status">正在加载…</p>
      <div v-else-if="!items.length" class="panel empty" data-empty>暂无 API 定义</div>
      <table v-else data-api-list><thead><tr><th>名称</th><th>方法与路径</th><th>版本</th><th>权限</th><th>状态</th><th>操作</th></tr></thead>
        <tbody><tr v-for="item in filteredItems" :key="item.id" :data-api-id="item.id"><td>{{ item.name }}</td><td><code data-api-path>{{ item.method }} {{ item.path }}</code></td><td>{{ item.version }}</td><td>{{ item.requiredPermission }}</td><td><span class="pill">{{ item.status }}</span></td><td class="actions"><button type="button" data-edit :disabled="mutationBusy" @click="edit(item)">编辑</button><button v-if="item.status === 'draft' || item.status === 'disabled'" type="button" data-publish :disabled="mutationBusy" @click="action(item, 'publish')">发布</button><button v-if="item.status === 'published'" type="button" data-disable :disabled="mutationBusy" @click="action(item, 'disable')">停用</button><button v-if="item.status === 'disabled'" type="button" data-enable :disabled="mutationBusy" @click="action(item, 'enable')">启用</button><button type="button" class="danger" data-delete :disabled="mutationBusy" @click="remove(item)">删除</button></td></tr><tr v-if="filteredItems.length === 0"><td colspan="6">无匹配 API</td></tr></tbody>
      </table>
    </section>
    <section v-else>
      <div class="toolbar"><input v-model.trim="logsKeyword" data-filter-keyword placeholder="搜索请求 ID、API 或主体"><span class="hint" data-logs-count>日志 {{ filteredLogs.length }} 条</span><span class="spacer"></span><button type="button" data-logs-refresh data-refresh-logs :disabled="busy" @click="load">刷新日志</button></div>
      <p v-if="error" class="err-box" role="alert" data-logs-error>{{ error }}</p><p v-if="busy" role="status">正在加载…</p>
      <div v-else-if="!logs.length" class="panel empty" data-logs-empty data-log-empty>暂无调用日志</div>
      <table v-else data-call-log-list data-log-list><thead><tr><th>请求 ID</th><th>API</th><th>主体</th><th>状态码</th><th>延迟</th><th>结果</th><th>时间</th></tr></thead><tbody><tr v-for="item in filteredLogs" :key="item.requestId"><td><code data-request-id>{{ item.requestId }}</code></td><td>{{ item.apiId }}</td><td>{{ item.principal }}</td><td>{{ item.statusCode }}</td><td>{{ item.latencyMs }}ms</td><td>{{ item.result }}</td><td>{{ item.requestedAt }}</td></tr><tr v-if="filteredLogs.length === 0"><td colspan="7">无匹配日志</td></tr></tbody></table>
    </section>
    <div v-if="editing" class="mask" data-editor-mask @click.self="editing = false"><form role="dialog" aria-modal="true" aria-label="API 定义编辑" @submit.prevent="save"><h2>{{ editingId ? '编辑 API' : '新建 API' }}</h2><label>名称<input v-model.trim="draft.name" required data-name></label><label>路径<input v-model.trim="draft.path" required data-path placeholder="/rebuild/..."></label><label>方法<select v-model="draft.method"><option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option></select></label><label>版本<input v-model.trim="draft.version" required></label><label>权限<input v-model.trim="draft.requiredPermission" required></label><label>说明<textarea v-model="draft.description" /></label><footer><button type="button" :disabled="mutationBusy" @click="editing = false">取消</button><button class="primary" data-save :disabled="mutationBusy">保存</button></footer></form></div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { openapiAdminApi, type ApiCallLogRecord, type ApiDefinitionInput, type ApiDefinitionRecord } from '../services/rebuild/openapiAdminApi'

const tab = ref<'definitions' | 'logs'>('definitions')
/** D13 列表搜索：两个列表各自前端过滤，不触发后端。 */
const definitionKeyword = ref('')
const logsKeyword = ref('')
const filteredItems = computed(() => {
  const keyword = definitionKeyword.value.toLowerCase()
  if (keyword === '') return items.value
  return items.value.filter((item) => item.name.toLowerCase().includes(keyword) || `${item.method} ${item.path}`.toLowerCase().includes(keyword))
})
const filteredLogs = computed(() => {
  const keyword = logsKeyword.value.toLowerCase()
  if (keyword === '') return logs.value
  return logs.value.filter((log) => log.requestId.toLowerCase().includes(keyword) || String(log.apiId).toLowerCase().includes(keyword) || log.principal.toLowerCase().includes(keyword))
})
const items = ref<ApiDefinitionRecord[]>([])
const logs = ref<ApiCallLogRecord[]>([])
const busy = ref(false)
const mutationBusy = ref(false)
const error = ref('')
const editing = ref(false)
const editingId = ref<number>()
const draft = reactive<ApiDefinitionInput>({ name: '', path: '/rebuild/', method: 'GET', version: 'v1', description: '', requiredPermission: 'security:read' })
const message = (cause: unknown) => cause instanceof Error ? cause.message : String(cause)

async function load() {
  busy.value = true
  error.value = ''
  try {
    if (tab.value === 'definitions') items.value = await openapiAdminApi.list()
    else logs.value = (await openapiAdminApi.callLogs({ limit: 100 })).list
  } catch (cause) { error.value = message(cause) } finally { busy.value = false }
}
watch(tab, load)
function openCreate() { error.value = ''; editingId.value = undefined; Object.assign(draft, { name: '', path: '/rebuild/', method: 'GET', version: 'v1', description: '', requiredPermission: 'security:read' }); editing.value = true }
function edit(item: ApiDefinitionRecord) { error.value = ''; editingId.value = item.id; Object.assign(draft, item); editing.value = true }
async function save() {
  if (mutationBusy.value) return
  mutationBusy.value = true
  error.value = ''
  try { if (editingId.value) await openapiAdminApi.update(editingId.value, { ...draft }); else await openapiAdminApi.create({ ...draft }); editing.value = false; await load() } catch (cause) { error.value = message(cause) } finally { mutationBusy.value = false }
}
async function action(item: ApiDefinitionRecord, operation: 'publish' | 'disable' | 'enable') { if (mutationBusy.value) return; mutationBusy.value = true; error.value = ''; try { await openapiAdminApi[operation](item.id); await load() } catch (cause) { error.value = message(cause) } finally { mutationBusy.value = false } }
async function remove(item: ApiDefinitionRecord) { if (mutationBusy.value || !globalThis.confirm(`删除“${item.name}”？`)) return; mutationBusy.value = true; error.value = ''; try { await openapiAdminApi.remove(item.id); await load() } catch (cause) { error.value = message(cause) } finally { mutationBusy.value = false } }
onMounted(load)
</script>

<style scoped>
.pg{max-width:1200px;margin:auto;padding:28px 24px;color:var(--text)}.pg-head,.toolbar,.tabs,.actions{display:flex;align-items:center;gap:10px}.pg-head{justify-content:space-between}.pg-head h1{margin:0}.pg-head p,.hint{color:var(--text-2)}.tabs{margin:18px 0;border-bottom:1px solid var(--border-strong)}.tabs button{border:0;border-bottom:2px solid transparent;background:transparent}.tabs .active{border-color:var(--primary);color:var(--primary)}.toolbar{margin:12px 0}.spacer{flex:1}.panel,table{background:var(--card);border:1px solid var(--border);border-radius:7px}.empty{padding:36px;text-align:center;color:var(--text-2)}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--border)}button,.op-btn{padding:7px 12px;border:1px solid var(--border-strong);border-radius:5px;background:var(--card);color:inherit;cursor:pointer;text-decoration:none}.primary{background:var(--primary);color:var(--card);border-color:var(--primary)}.danger{color:var(--danger)}.pill{padding:2px 7px;border-radius:999px;background:var(--border)}.err-box{padding:9px 12px;background:var(--danger-bg);color:var(--danger)}.mask{position:fixed;inset:0;background:color-mix(in srgb, var(--text) 40%, transparent);display:grid;place-items:center;z-index:30}.mask form{width:min(500px,calc(100vw - 40px));display:grid;gap:12px;background:var(--card);padding:24px;border-radius:8px}.mask label{display:grid;gap:5px}.mask input,.mask select,.mask textarea{padding:8px}.mask footer{display:flex;justify-content:flex-end;gap:8px}
</style>

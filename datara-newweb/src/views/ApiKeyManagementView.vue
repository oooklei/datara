<template>
  <main class="pg" aria-label="API-Key 管理">
    <header class="pg-head">
      <div><h1>API-Key 管理</h1><p>管理受控 API 的访问凭据；原始 Key 仅在签发或轮换后显示一次。</p></div>
      <a class="op-btn" href="/open/api" data-goto-api>API 管理</a>
    </header>
    <div class="toolbar">
      <input v-model.trim="filterKeyword" data-filter-keyword placeholder="搜索名称、前缀或状态">
      <span class="hint" data-apikey-count>Key {{ visibleKeys.length }} 条</span><span class="spacer"></span>
      <button type="button" class="op-btn" data-refresh :disabled="busy" @click="reload">刷新</button>
      <button type="button" class="op-btn primary" data-create data-issue @click="openIssue">+ 签发 API-Key</button>
    </div>
    <p v-if="error" class="err-box" role="alert" data-error>{{ error }}</p>
    <p v-if="busy" role="status">正在加载…</p>
    <div v-else-if="!keys.length" class="panel empty" data-empty>暂无 API-Key</div>
    <table v-else data-apikey-list data-key-list>
      <thead><tr><th>名称</th><th>前缀</th><th>权限范围</th><th>项目范围</th><th>状态</th><th>过期时间</th><th>操作</th></tr></thead>
      <tbody><tr v-for="key in visibleKeys" :key="key.id" :data-key-id="key.id">
        <td>{{ key.name }}</td><td><code data-key-prefix>{{ key.keyPrefix }}</code></td><td>{{ key.scopes.permissions.join(', ') || '—' }}</td>
        <td>{{ key.scopes.projectIds.join(', ') || '全局' }}</td><td><span class="pill">{{ key.status }}</span></td><td>{{ key.expiresAt || '永不过期' }}</td>
        <td class="actions"><button type="button" class="mini-btn" data-rotate :disabled="key.status !== 'active' || busy" @click="rotate(key)">轮换</button><button type="button" class="mini-btn danger" data-revoke :disabled="key.status !== 'active' || busy" @click="revoke(key)">撤销</button></td>
      </tr><tr v-if="visibleKeys.length === 0"><td colspan="7">无匹配 Key</td></tr></tbody>
    </table>

    <div v-if="plainKey" class="mask" @click.self="closePlainKey">
      <section ref="issuedRef" class="issued" role="dialog" aria-modal="true" aria-label="一次性 API-Key" data-issued :style="issuedDragStyle">
        <h2 ref="issuedHdRef" @pointerdown="onIssuedDragStart">请立即保存 API-Key</h2><p>关闭后无法再次查看，系统和浏览器均不会持久化明文。</p>
        <code data-plain-key>{{ plainKey }}</code>
        <p v-if="copyStatus" class="hint" role="status">{{ copyStatus }}</p>
        <footer><button type="button" class="mini-btn" data-copy-key @click="copyPlainKey">复制</button><button type="button" class="mini-btn primary" data-close-key @click="closePlainKey">已保存，关闭</button></footer>
      </section>
    </div>

    <div v-if="editing" class="mask" @click.self="editing = false">
      <form ref="editFormRef" role="dialog" aria-modal="true" aria-label="签发 API-Key" :style="editDragStyle" @submit.prevent="issue">
        <h2 ref="editHdRef" @pointerdown="onEditDragStart">签发 API-Key</h2>
        <label>名称<input v-model.trim="draft.name" required data-name></label>
        <label>权限（逗号分隔）<input v-model="permissionsText" required data-permissions placeholder="security:read,workflow:run"></label>
        <label>项目 ID（逗号分隔，留空表示全局）<input v-model="projectIdsText" data-projects inputmode="numeric"></label>
        <label>过期时间<input v-model="expiresText" data-expires type="datetime-local"></label>
        <footer><button type="button" class="mini-btn" @click="editing = false">取消</button><button class="mini-btn primary" data-save :disabled="busy">签发</button></footer>
      </form>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useDraggable } from '../composables/useDraggable'
import { openapiAdminKeyApi, type ApiKeyInput, type ApiKeyRecord } from '../services/rebuild/openapiAdminApi'

const keys = ref<ApiKeyRecord[]>([])
const filterKeyword = ref('')
/** D13 列表搜索：前端过滤 name/keyPrefix/status，不触发后端。 */
const visibleKeys = computed(() => {
  const keyword = filterKeyword.value.toLowerCase()
  if (keyword === '') return keys.value
  return keys.value.filter((key) =>
    key.name.toLowerCase().includes(keyword) ||
    key.keyPrefix.toLowerCase().includes(keyword) ||
    key.status.toLowerCase().includes(keyword))
})
const busy = ref(false)
const error = ref('')
const editing = ref(false)
const plainKey = ref('')

/* G14 §2.2：双弹窗默认可拖动 + 视口钳制 + 位置记忆（把手=h2 标题） */
const issuedRef = ref<HTMLElement | null>(null)
const issuedHdRef = ref<HTMLElement | null>(null)
const { dragStyle: issuedDragStyle, onHandlePointerdown: onIssuedDragStart } = useDraggable(issuedRef, issuedHdRef, { storageKey: 'apikey.issued' })
const editFormRef = ref<HTMLFormElement | null>(null)
const editHdRef = ref<HTMLElement | null>(null)
const { dragStyle: editDragStyle, onHandlePointerdown: onEditDragStart } = useDraggable(editFormRef, editHdRef, { storageKey: 'apikey.edit' })
const copyStatus = ref('')
const permissionsText = ref('')
const projectIdsText = ref('')
const expiresText = ref('')
const draft = reactive<ApiKeyInput>({ name: '', scopes: { permissions: [], projectIds: [] }, expiresAt: null })
const message = (cause: unknown) => cause instanceof Error ? cause.message : String(cause)

async function reload() {
  busy.value = true
  error.value = ''
  try { keys.value = await openapiAdminKeyApi.list() } catch (cause) { error.value = message(cause) } finally { busy.value = false }
}
function openIssue() {
  draft.name = ''
  draft.expiresAt = null
  permissionsText.value = ''
  projectIdsText.value = ''
  expiresText.value = ''
  editing.value = true
}
async function issue() {
  error.value = ''
  busy.value = true
  try {
    draft.scopes = {
      permissions: permissionsText.value.split(',').map((value) => value.trim()).filter(Boolean),
      projectIds: projectIdsText.value.split(',').map((value) => Number(value.trim())).filter((value) => Number.isInteger(value) && value > 0),
    }
    draft.expiresAt = expiresText.value ? new Date(expiresText.value).toISOString() : null
    const result = await openapiAdminKeyApi.issue({ ...draft, scopes: { ...draft.scopes } })
    plainKey.value = result.plainKey
    copyStatus.value = ''
    editing.value = false
    await reload()
  } catch (cause) { error.value = message(cause) } finally { busy.value = false }
}
async function rotate(key: ApiKeyRecord) {
  if (!globalThis.confirm(`轮换 API-Key“${key.name}”？旧 Key 将立即失效。`)) return
  error.value = ''
  try { const result = await openapiAdminKeyApi.rotate(key.id); plainKey.value = result.plainKey; copyStatus.value = ''; await reload() } catch (cause) { error.value = message(cause) }
}
async function revoke(key: ApiKeyRecord) {
  if (!globalThis.confirm(`撤销 API-Key“${key.name}”？`)) return
  error.value = ''
  try { await openapiAdminKeyApi.revoke(key.id); await reload() } catch (cause) { error.value = message(cause) }
}
async function copyPlainKey() {
  try { await navigator.clipboard.writeText(plainKey.value); copyStatus.value = '已复制到剪贴板' } catch { copyStatus.value = '复制失败，请手动复制' }
}
function closePlainKey() { plainKey.value = ''; copyStatus.value = '' }
onMounted(reload)
</script>

<style scoped>
.pg{max-width:1180px;margin:auto;padding:28px 24px;color:var(--text)}.pg-head,.toolbar,.actions{display:flex;align-items:center;gap:10px}.pg-head{justify-content:space-between}.pg-head h1{margin:0}.pg-head p,.hint{color:var(--text-2)}.toolbar{margin:18px 0}.spacer{flex:1}.panel,table{background:var(--card);border:1px solid var(--border);border-radius:7px}.empty{padding:36px;text-align:center;color:var(--text-2)}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--border)}.pill{padding:2px 7px;border-radius:999px;background:var(--border)}.err-box{padding:9px 12px;background:var(--danger-bg);color:var(--danger)}.mask{position:fixed;inset:0;background:var(--mask-bg);display:grid;place-items:center;z-index:30}.mask form,.issued{width:min(560px,calc(100vw - 40px));display:grid;gap:12px;background:var(--card);padding:24px;border-radius:8px}.mask label{display:grid;gap:5px}.mask input{padding:8px}.mask footer{display:flex;justify-content:flex-end;gap:8px}.issued code{display:block;padding:12px;background:var(--bg);overflow-wrap:anywhere}
.issued h2,.mask form h2{cursor:grab;user-select:none}
.issued h2:active,.mask form h2:active{cursor:grabbing}
</style>

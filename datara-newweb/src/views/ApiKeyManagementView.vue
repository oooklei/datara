<template>
  <main class="key-page" aria-label="API-Key 管理">
    <header><div><h1>API-Key 管理</h1><p>管理受控 API 的访问凭据；原始 Key 仅在签发或轮换后显示一次。</p></div><button type="button" data-issue @click="openIssue">签发 API-Key</button></header>
    <p v-if="busy" role="status">正在加载…</p><p v-if="error" role="alert">{{ error }}</p>
    <p v-if="!busy && !keys.length" data-empty>暂无 API-Key</p>
    <table v-else data-key-list><thead><tr><th>名称</th><th>前缀</th><th>权限范围</th><th>项目范围</th><th>状态</th><th>过期时间</th><th>操作</th></tr></thead>
      <tbody><tr v-for="key in keys" :key="key.id" :data-key-id="key.id"><td>{{ key.name }}</td><td><code>{{ key.keyPrefix }}</code></td><td>{{ key.scopes.permissions.join(', ') || '—' }}</td><td>{{ key.scopes.projectIds.join(', ') || '全局' }}</td><td>{{ key.status === 'active' ? '启用' : '已撤销' }}</td><td>{{ key.expiresAt || '永不过期' }}</td><td class="actions"><button type="button" data-rotate :disabled="key.status !== 'active'" @click="rotate(key)">轮换</button><button type="button" data-revoke :disabled="key.status !== 'active'" @click="revoke(key)">撤销</button></td></tr></tbody>
    </table>
    <div v-if="plainKey" class="mask" @click.self="plainKey = ''"><section role="dialog" aria-modal="true" aria-label="一次性 API-Key"><h2>请立即复制 API-Key</h2><p>关闭后无法再次查看原始凭据。</p><code data-plain-key>{{ plainKey }}</code><button type="button" data-close-key @click="plainKey = ''">已复制，关闭</button></section></div>
    <div v-if="editing" class="mask" @click.self="editing = false"><form role="dialog" aria-modal="true" aria-label="签发 API-Key" @submit.prevent="issue"><h2>签发 API-Key</h2><label>名称<input v-model.trim="draft.name" required data-name></label><label>权限范围<input v-model.trim="permissionsText" placeholder="security:read, workflow:run" data-permissions></label><label>项目 ID<input v-model.trim="projectIdsText" placeholder="逗号分隔，留空为全局" data-projects></label><label>过期时间<input v-model="draft.expiresAt" type="datetime-local" data-expires></label><footer><button type="button" @click="editing = false">取消</button><button type="submit" data-save>签发</button></footer></form></div>
  </main>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { openapiAdminKeyApi, type ApiKeyInput, type ApiKeyRecord } from '../services/rebuild/openapiAdminApi'
const keys = ref<ApiKeyRecord[]>([]), busy = ref(false), error = ref(''), editing = ref(false), plainKey = ref('')
const permissionsText = ref(''), projectIdsText = ref('')
const draft = reactive<ApiKeyInput>({ name: '', scopes: { permissions: [], projectIds: [] }, expiresAt: null })
const message = (e: unknown) => e instanceof Error ? e.message : String(e)
async function reload() { busy.value = true; error.value = ''; try { keys.value = await openapiAdminKeyApi.list() } catch (e) { error.value = message(e) } finally { busy.value = false } }
function openIssue() { draft.name = ''; draft.expiresAt = null; permissionsText.value = ''; projectIdsText.value = ''; editing.value = true }
async function issue() { try { draft.scopes = { permissions: permissionsText.value.split(',').map(v => v.trim()).filter(Boolean), projectIds: projectIdsText.value.split(',').map(v => v.trim()).filter(Boolean).map(Number).filter(Number.isInteger) }; const result = await openapiAdminKeyApi.issue({ ...draft, scopes: { ...draft.scopes } }); editing.value = false; plainKey.value = result.plainKey; await reload() } catch (e) { error.value = message(e) } }
async function rotate(key: ApiKeyRecord) { if (!globalThis.confirm(`轮换 API-Key“${key.name}”？`)) return; try { plainKey.value = (await openapiAdminKeyApi.rotate(key.id)).plainKey; await reload() } catch (e) { error.value = message(e) } }
async function revoke(key: ApiKeyRecord) { if (!globalThis.confirm(`撤销 API-Key“${key.name}”？`)) return; try { await openapiAdminKeyApi.revoke(key.id); await reload() } catch (e) { error.value = message(e) } }
onMounted(reload)
</script>
<style scoped>.key-page{max-width:1180px;margin:auto;padding:32px 24px;color:#172033}.key-page>header{display:flex;justify-content:space-between;align-items:center}.key-page h1{margin:0}.key-page header p{color:#64748b}button{cursor:pointer;padding:7px 12px}button:disabled{cursor:not-allowed;opacity:.5}table{width:100%;border-collapse:collapse;background:#fff}th,td{text-align:left;padding:11px;border-bottom:1px solid #e2e8f0}.actions{display:flex;gap:6px}.mask{position:fixed;inset:0;background:#0f172a66;display:grid;place-items:center}.mask form,.mask section{width:min(500px,calc(100vw - 40px));display:grid;gap:12px;background:#fff;padding:24px;border-radius:10px}.mask label{display:grid;gap:5px}.mask input{padding:8px}.mask code{word-break:break-all;padding:12px;background:#f1f5f9;border-radius:6px}.mask footer{display:flex;justify-content:flex-end;gap:8px}</style>

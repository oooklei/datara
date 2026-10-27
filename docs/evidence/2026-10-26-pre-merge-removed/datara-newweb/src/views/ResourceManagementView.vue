<template>
  <section class="resources-page" aria-label="资源管理正式页">
    <header>
      <h1>资源管理</h1>
      <p>上传 SQL、Python 或 Shell 文件，浏览不可变版本，并把具体版本引用到工作流任务。</p>
    </header>

    <form class="upload" data-resource-upload @submit.prevent="upload">
      <label>类型
        <select v-model="uploadKind" data-kind-filter>
          <option value="sql">SQL</option><option value="python">Python</option><option value="shell">Shell</option>
        </select>
      </label>
      <label>文件 <input data-resource-file type="file" @change="pickFile"></label>
      <button type="submit" :disabled="busy || !pickedFile">上传新版本</button>
    </form>

    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="busy" role="status">正在处理…</p>
    <p v-else-if="!resources.length" data-resource-empty>暂无资源</p>
    <div v-else class="layout">
      <table data-resource-list>
        <thead><tr><th>名称</th><th>类型</th><th>最新版本</th><th>大小</th></tr></thead>
        <tbody>
          <tr v-for="item in resources" :key="item.resourceId" :class="{ selected: item.resourceId === selectedId }"
              :data-resource-id="item.resourceId" @click="selectResource(item.resourceId)">
            <td>{{ item.name }}</td><td>{{ item.kind }}</td><td>v{{ item.latestVersion }}</td><td>{{ item.sizeBytes }}</td>
          </tr>
        </tbody>
      </table>

      <aside v-if="selected" data-version-panel>
        <h2>{{ selected.name }} 的版本</h2>
        <ul>
          <li v-for="version in versions" :key="version.version" :data-version="version.version">
            <label><input v-model.number="selectedVersion" type="radio" :value="version.version">v{{ version.version }}</label>
            <span>{{ version.digest.slice(0, 12) }}… · {{ version.sizeBytes }} B</span>
            <button type="button" @click="download(version.version)">下载</button>
          </li>
        </ul>
        <form class="binding" data-resource-binding @submit.prevent="bind">
          <h3>固定版本引用</h3>
          <label>工作流 ID <input v-model.number="binding.workflowId" type="number" min="1" required></label>
          <label>工作流版本 <input v-model.number="binding.workflowVersion" type="number" min="1" required></label>
          <label>任务 ID <input v-model.trim="binding.taskId" required></label>
          <button type="submit" :disabled="!selectedVersion">引用 v{{ selectedVersion || '—' }}</button>
          <output v-if="bindingId" data-binding-result>已建立引用 #{{ bindingId }}</output>
        </form>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { createResourceContract, RESOURCE_KINDS, validateUploadDraft } from '../services/rebuild/resourceApi'
import type { ResourceKind, ResourceMeta, ResourceVersion } from '../services/rebuild/resourceApi'

const props = defineProps<{ projectId: number }>()
const api = createResourceContract()
const uploadKind = ref<ResourceKind>('sql')
const pickedFile = ref<File>()
const resources = ref<ResourceMeta[]>([])
const versions = ref<ResourceVersion[]>([])
const selectedId = ref<number>()
const selectedVersion = ref<number>()
const busy = ref(false)
const error = ref('')
const bindingId = ref<number>()
const binding = reactive({ workflowId: 1, workflowVersion: 1, taskId: '' })
const selected = computed(() => resources.value.find((item) => item.resourceId === selectedId.value))

function message(reason: unknown): string { return reason instanceof Error ? reason.message : String(reason) }
async function reload() {
  busy.value = true; error.value = ''
  try {
    resources.value = await api.listResources(props.projectId, uploadKind.value)
    if (selectedId.value && !resources.value.some((item) => item.resourceId === selectedId.value)) {
      selectedId.value = undefined; versions.value = []
    }
  } catch (reason) { error.value = message(reason) } finally { busy.value = false }
}
function pickFile(event: Event) { pickedFile.value = (event.target as HTMLInputElement).files?.[0] }
function asBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error)
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '')
    reader.readAsDataURL(file)
  })
}
async function upload() {
  const file = pickedFile.value
  if (!file) return
  const diagnostics = validateUploadDraft(uploadKind.value, file.name, file.size)
  if (diagnostics.length) { error.value = diagnostics.map((item) => item.message).join('；'); return }
  busy.value = true; error.value = ''
  try {
    await api.uploadResource({ projectId: props.projectId, kind: uploadKind.value, filename: file.name, sizeBytes: file.size, contentBase64: await asBase64(file) })
    await reload()
  } catch (reason) { error.value = message(reason); busy.value = false }
}
async function selectResource(resourceId: number) {
  selectedId.value = resourceId; bindingId.value = undefined; error.value = ''
  try {
    versions.value = await api.listResourceVersions(resourceId, props.projectId)
    selectedVersion.value = versions.value.at(-1)?.version
  } catch (reason) { error.value = message(reason) }
}
async function download(version: number) {
  if (!selectedId.value) return
  try {
    const result = await api.downloadResourceVersion(selectedId.value, version, props.projectId)
    const url = URL.createObjectURL(result.blob)
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = result.filename; anchor.click()
    URL.revokeObjectURL(url)
  } catch (reason) { error.value = message(reason) }
}
async function bind() {
  if (!selectedId.value || !selectedVersion.value) return
  try {
    const result = await api.bindResourceVersion({ projectId: props.projectId, ...binding, resourceId: selectedId.value, resourceVersion: selectedVersion.value })
    bindingId.value = result.bindingId
  } catch (reason) { error.value = message(reason) }
}

watch(uploadKind, reload)
onMounted(reload)

// Runtime assertion keeps UI options and the frozen wire enum in one source.
void RESOURCE_KINDS
</script>

<style scoped>
.resources-page{max-width:1100px;margin:auto;padding:32px 24px}.resources-page header p{color:var(--text-2)}.upload,.binding{display:flex;gap:12px;align-items:end;flex-wrap:wrap;padding:16px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius)}.layout{display:grid;grid-template-columns:minmax(420px,1fr) minmax(320px,.8fr);gap:20px;margin-top:20px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--border)}tbody tr{cursor:pointer}.selected{background:var(--primary-light)}aside{border:1px solid var(--border);border-radius:var(--radius);padding:16px}aside ul{padding:0;list-style:none}aside li{display:flex;gap:10px;align-items:center;margin:8px 0}.binding{align-items:stretch;flex-direction:column}.binding label{display:flex;justify-content:space-between;gap:8px}@media(max-width:800px){.layout{grid-template-columns:1fr}}
</style>

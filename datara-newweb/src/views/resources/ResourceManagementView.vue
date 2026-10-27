<template>
  <section class="resource-page" aria-label="资源管理">
    <header class="resource-head">
      <div><h1>资源管理</h1><p>管理 SQL、Python、Shell 资源及其不可变版本。</p></div>
      <label v-if="!hasProjectProp">项目
        <select v-model="selectedProject" data-project-select @change="load">
          <option value="">请选择项目</option>
          <option v-for="project in projects" :key="project.id" :value="String(project.id)">{{ project.name }}</option>
        </select>
      </label>
      <select v-model="kind" aria-label="资源类型" @change="load"><option value="">全部类型</option><option value="sql">SQL</option><option value="python">Python</option><option value="shell">Shell</option></select>
      <label class="upload-control">Upload
        <select v-model="uploadKind" aria-label="Upload resource type"><option value="sql">SQL</option><option value="python">Python</option><option value="shell">Shell</option></select>
        <input type="file" :accept="acceptFor(uploadKind)" @change="onFile" />
      </label>
    </header>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <table v-else><thead><tr><th>名称</th><th>类型</th><th>版本</th><th>状态</th><th>大小</th><th>操作</th></tr></thead>
      <tbody><tr v-for="item in items" :key="item.resourceId"><td>{{ item.name }}</td><td>{{ item.kind }}</td><td>v{{ item.latestVersion }}</td><td>active</td><td>{{ item.sizeBytes }} bytes</td><td><button type="button" data-view-versions @click="openVersions(item)">查看版本</button></td></tr><tr v-if="!loading && !items.length"><td colspan="6">暂无资源</td></tr></tbody>
    </table>
    <p v-if="loading">加载中…</p>
    <div v-if="selectedResource" class="mask" data-version-mask @click.self="closeVersions">
      <section class="version-dialog" role="dialog" aria-modal="true" :aria-label="`${selectedResource.name} 版本历史`">
        <header><div><h2>{{ selectedResource.name }}</h2><p>不可变版本历史</p></div><button type="button" aria-label="关闭版本历史" @click="closeVersions">关闭</button></header>
        <p v-if="versionError" class="error" role="alert">{{ versionError }}</p>
        <p v-else-if="versionsLoading" role="status">正在加载版本…</p>
        <table v-else><thead><tr><th>版本</th><th>大小</th><th>摘要</th><th>上传时间</th></tr></thead>
          <tbody><tr v-for="version in versions" :key="version.version"><td>v{{ version.version }}</td><td>{{ version.sizeBytes }} bytes</td><td><code>{{ version.digest }}</code></td><td>{{ version.uploadedAt }}</td></tr><tr v-if="!versions.length"><td colspan="4">暂无版本</td></tr></tbody>
        </table>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { createResourceContract, validateUploadDraft, type ResourceKind, type ResourceMeta, type ResourceVersion } from '../../services/rebuild/resourceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const props = defineProps<{ projectId?: number }>()
const api = createResourceContract()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const kind = ref<ResourceKind | ''>('')
const items = ref<ResourceMeta[]>([])
const loading = ref(false)
const error = ref('')
const selectedResource = ref<ResourceMeta | null>(null)
const versions = ref<ResourceVersion[]>([])
const versionsLoading = ref(false)
const versionError = ref('')
let versionsRequest = 0
let listRequest = 0
const uploadKind = ref<ResourceKind>('sql')
const acceptFor = (value: ResourceKind) => ({ sql: '.sql', python: '.py', shell: '.sh' })[value]
const hasProjectProp = computed(() => Number.isInteger(props.projectId) && Number(props.projectId) > 0)
const projectId = computed<number | null>(() => {
  if (hasProjectProp.value) return Number(props.projectId)
  const selected = Number(selectedProject.value)
  return selectedProject.value !== '' && Number.isInteger(selected) && selected > 0 ? selected : null
})

async function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (projectId.value === null) { error.value = '请先选择项目'; input.value = ''; return }
  const diagnostics = validateUploadDraft(uploadKind.value, file.name, file.size)
  if (diagnostics.length) { error.value = diagnostics.map((d) => d.message).join('; '); input.value = ''; return }
  try {
    const bytes = new Uint8Array(await file.arrayBuffer())
    let binary = ''
    for (const byte of bytes) binary += String.fromCharCode(byte)
    await api.uploadResource({ projectId: projectId.value, kind: uploadKind.value, filename: file.name, sizeBytes: file.size, contentBase64: btoa(binary) })
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Upload failed' }
  finally { input.value = '' }
}

async function load() {
  const request = ++listRequest
  const targetProjectId = projectId.value
  if (targetProjectId === null) { items.value = []; loading.value = false; return }
  loading.value = true; error.value = ''
  try {
    const result = await api.listResources(targetProjectId, kind.value || undefined)
    if (request === listRequest) items.value = result
  } catch (cause) {
    if (request === listRequest) error.value = cause instanceof Error ? cause.message : '资源加载失败'
  } finally {
    if (request === listRequest) loading.value = false
  }
}

async function openVersions(resource: ResourceMeta) {
  if (projectId.value === null) return
  const request = ++versionsRequest
  selectedResource.value = resource
  versions.value = []
  versionError.value = ''
  versionsLoading.value = true
  try {
    const result = await api.listResourceVersions(resource.resourceId, projectId.value)
    if (request === versionsRequest) versions.value = result
  } catch (cause) {
    if (request === versionsRequest) versionError.value = cause instanceof Error ? cause.message : '版本加载失败'
  } finally {
    if (request === versionsRequest) versionsLoading.value = false
  }
}

function closeVersions() {
  versionsRequest += 1
  selectedResource.value = null
  versions.value = []
  versionsLoading.value = false
  versionError.value = ''
}
// Vue reuses the segment component when only :projectId changes.  Reload on
// prop changes as well as the initial mount so a deep-link switch never shows
// resources from the previous project.
watch(() => props.projectId, () => {
  closeVersions()
  if (hasProjectProp.value) void load()
}, { immediate: true })

onMounted(async () => {
  if (hasProjectProp.value) return
  try {
    const page = await listProjects()
    projects.value = page.list
    if (projects.value.length > 0) selectedProject.value = String(projects.value[0].id)
    await load()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '项目加载失败'
  }
})
</script>

<style scoped>
.resource-page{padding:24px}.resource-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.resource-head h1{margin:0 0 6px}.resource-head p{margin:0;color:var(--text-2)}.resource-head select{padding:8px 12px}table{width:100%;border-collapse:collapse;background:var(--card)}th,td{padding:10px 12px;border-bottom:1px solid var(--border);text-align:left}.error{color:var(--danger)}.mask{position:fixed;inset:0;z-index:30;display:grid;place-items:center;padding:24px;background:color-mix(in srgb, var(--text) 40%, transparent)}.version-dialog{width:min(880px,100%);max-height:calc(100vh - 48px);overflow:auto;padding:22px;background:var(--card);border-radius:10px;box-shadow:0 20px 45px color-mix(in srgb, var(--text) 20%, transparent)}.version-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:16px}.version-dialog h2,.version-dialog p{margin:0}.version-dialog header p{color:var(--text-2)}.version-dialog code{overflow-wrap:anywhere}
</style>

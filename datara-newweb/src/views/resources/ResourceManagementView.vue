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
    <table v-else><thead><tr><th>名称</th><th>类型</th><th>版本</th><th>状态</th><th>更新时间</th></tr></thead>
      <tbody><tr v-for="item in items" :key="item.resourceId"><td>{{ item.name }}</td><td>{{ item.kind }}</td><td>v{{ item.latestVersion }}</td><td>active</td><td>{{ item.sizeBytes }} bytes</td></tr><tr v-if="!loading && !items.length"><td colspan="5">暂无资源</td></tr></tbody>
    </table>
    <p v-if="loading">加载中…</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { createResourceContract, validateUploadDraft, type ResourceKind, type ResourceMeta } from '../../services/rebuild/resourceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const props = defineProps<{ projectId?: number }>()
const api = createResourceContract()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const kind = ref<ResourceKind | ''>('')
const items = ref<ResourceMeta[]>([])
const loading = ref(false)
const error = ref('')
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
  if (projectId.value === null) { items.value = []; return }
  loading.value = true; error.value = ''
  try { items.value = await api.listResources(projectId.value, kind.value || undefined) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '资源加载失败' }
  finally { loading.value = false }
}
// Vue reuses the segment component when only :projectId changes.  Reload on
// prop changes as well as the initial mount so a deep-link switch never shows
// resources from the previous project.
watch(() => props.projectId, () => { if (hasProjectProp.value) void load() }, { immediate: true })

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
.resource-page{padding:24px}.resource-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.resource-head h1{margin:0 0 6px}.resource-head p{margin:0;color:#64748b}.resource-head select{padding:8px 12px}table{width:100%;border-collapse:collapse;background:#fff}th,td{padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:left}.error{color:#b91c1c}
</style>

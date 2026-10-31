<template>
  <main class="pg" aria-label="资源管理">
    <header class="pg-head">
      <h1 class="sec-head">资源管理</h1>
      <p class="pg-desc">管理 SQL、Python、Shell 脚本资源及其不可变版本；试运行与上线节点按版本引用。</p>
    </header>

    <div class="toolbar">
      <select v-model="kind" class="kw" aria-label="资源类型" @change="load">
        <option value="">全部类型</option>
        <option value="sql">SQL</option>
        <option value="python">Python</option>
        <option value="shell">Shell</option>
      </select>
      <span class="spacer"></span>
      <button type="button" class="op-btn primary" data-upload @click="pickFile">上传资源</button>
      <input ref="fileInput" type="file" :accept="acceptFor(uploadKind)" hidden data-upload-input @change="onFile" />
    </div>

    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn" :disabled="loading" @click="load">重试</button>
    </div>
    <p v-else-if="projectId === null" class="panel empty" data-no-project>请先选择项目</p>
    <template v-else>
      <div class="panel">
        <div class="tbl-toolbar">
          <span class="sec-head">资源清单</span>
          <span class="pill info">{{ filteredItems.length }}</span>
          <input v-model.trim="filterKeyword" data-filter-keyword placeholder="搜索名称或类型" />
          <span class="spacer"></span>
        </div>
        <table class="tbl" data-resource-list>
          <thead>
            <tr><th>名称</th><th>类型</th><th>版本</th><th>状态</th><th>大小（字节）</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in filteredItems" :key="item.resourceId">
              <td>{{ item.name }}</td>
              <td>{{ item.kind }}</td>
              <td>v{{ item.latestVersion }}</td>
              <td><span class="pill ok">启用</span></td>
              <td>{{ item.sizeBytes }}</td>
              <td class="actions">
                <button type="button" class="mini-btn" data-edit-resource @click="openEditor(item)">修改</button>
                <button type="button" class="mini-btn" data-view-versions @click="openVersions(item)">查看版本</button>
              </td>
            </tr>
            <tr v-if="!loading && !filteredItems.length"><td colspan="6" class="empty">{{ items.length ? '无匹配资源' : '暂无资源' }}</td></tr>
          </tbody>
        </table>
      </div>
    </template>
    <p v-if="loading" class="hint" role="status">加载中…</p>

    <div v-if="selectedResource" class="mask" data-version-mask @click.self="closeVersions">
      <section ref="versionDlgRef" class="dlg" role="dialog" aria-modal="true" :aria-label="`${selectedResource.name} 版本历史`" :style="versionDragStyle">
        <header ref="versionHdRef" class="dlg-hd" @pointerdown="onVersionDragStart">
          <div class="meta">
            <h2>{{ selectedResource.name }}</h2>
            <p>不可变版本历史</p>
          </div>
          <button type="button" class="x" aria-label="关闭版本历史" @click="closeVersions">×</button>
        </header>
        <div class="dlg-bd">
          <p v-if="versionError" class="err-box" role="alert">{{ versionError }}</p>
          <p v-else-if="versionsLoading" role="status">正在加载版本…</p>
          <table v-else class="tbl">
            <thead><tr><th>版本</th><th>大小（字节）</th><th>摘要</th><th>上传时间</th></tr></thead>
            <tbody>
              <tr v-for="version in versions" :key="version.version">
                <td>v{{ version.version }}</td>
                <td>{{ version.sizeBytes }}</td>
                <td><code>{{ version.digest }}</code></td>
                <td>{{ version.uploadedAt }}</td>
              </tr>
              <tr v-if="!versions.length"><td colspan="4">暂无版本</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <ResourceScriptEditorDialog
      v-if="editingResource && projectId !== null"
      :project-id="projectId"
      :resource="editingResource"
      @close="closeEditor"
      @saved="onSaved"
    />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDraggable } from '../../composables/useDraggable'
import ResourceScriptEditorDialog from './ResourceScriptEditorDialog.vue'
import { createResourceContract, validateUploadDraft, type ResourceKind, type ResourceMeta, type ResourceVersion } from '../../services/rebuild/resourceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const props = defineProps<{ projectId?: number }>()
const api = createResourceContract()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const kind = ref<ResourceKind | ''>('sql')
const items = ref<ResourceMeta[]>([])
const filterKeyword = ref('')
/** D13 列表搜索：前端过滤 name/kind，不触发后端。 */
const filteredItems = computed(() => {
  const keyword = filterKeyword.value.toLowerCase()
  if (keyword === '') return items.value
  return items.value.filter((item) => item.name.toLowerCase().includes(keyword) || item.kind.toLowerCase().includes(keyword))
})
const loading = ref(false)
const error = ref('')
const selectedResource = ref<ResourceMeta | null>(null)

/* G14 §2.2：版本弹窗默认可拖动 + 视口钳制 + 位置记忆（把手=header） */
const versionDlgRef = ref<HTMLElement | null>(null)
const versionHdRef = ref<HTMLElement | null>(null)
const { dragStyle: versionDragStyle, onHandlePointerdown: onVersionDragStart } = useDraggable(versionDlgRef, versionHdRef, { storageKey: 'resource.versions' })

const versions = ref<ResourceVersion[]>([])
const versionsLoading = ref(false)
const versionError = ref('')
let versionsRequest = 0
let listRequest = 0
/** 上传类型跟随列表类型筛选；「全部类型」时默认 SQL。 */
const uploadKind = computed<ResourceKind>(() => (kind.value === '' ? 'sql' : kind.value))
const acceptFor = (value: ResourceKind) => ({ sql: '.sql', python: '.py', shell: '.sh' })[value]
/** 上传入口：.op-btn 触发隐藏 file input（对齐 OrchestrationResourceFileView 模式）。 */
const fileInput = ref<HTMLInputElement | null>(null)
function pickFile(): void {
  fileInput.value?.click()
}
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
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '上传失败' }
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

/* 修改入口：脚本编辑弹窗（校验 / 试运行 / 追加不可变版本） */
const editingResource = ref<ResourceMeta | null>(null)

function openEditor(resource: ResourceMeta) {
  if (projectId.value === null) return
  closeVersions()
  editingResource.value = resource
}

function closeEditor() {
  editingResource.value = null
}

async function onSaved() {
  await load()
}
// Vue reuses the segment component when only :projectId changes.  Reload on
// prop changes as well as the initial mount so a deep-link switch never shows
// resources from the previous project.
watch(() => props.projectId, () => {
  closeVersions()
  closeEditor()
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
/* 版本历史弹窗：全局 .dlg 体系 + 宽度覆写（scoped 不外泄） */
.dlg { width: min(880px, calc(100vw - 48px)); }
.dlg-hd .meta { display: flex; flex-direction: column; line-height: 1.35; }
.dlg-hd .meta h2 { font-size: 14px; }
.dlg-hd .meta p { font-size: 11.5px; color: var(--text-3); font-weight: 400; }
.dlg-bd code { overflow-wrap: anywhere; }
</style>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  createResourceContract,
  validateUploadDraft,
  type ResourceKind,
  type ResourceMeta,
  type ResourceVersion,
} from '../services/rebuild/resourceApi'
import { createDatasourceContract, type DatasourceRecord } from '../services/rebuild/datasourceApi'
import VariableReferenceInput from './VariableReferenceInput.vue'

const props = defineProps<{
  projectId: number
  workflowId: number
  workflowVersion: number
  taskId: string
  kind: ResourceKind
  modelValue: Record<string, unknown>
}>()

const emit = defineEmits<{ 'update:modelValue': [value: Record<string, unknown>] }>()
const api = createResourceContract()
const currentParams = ref<Record<string, unknown>>({ ...props.modelValue })
const mode = ref<'inline' | 'resource'>(props.modelValue.sourceMode === 'resource' ? 'resource' : 'inline')
const resources = ref<ResourceMeta[]>([])
const versions = ref<ResourceVersion[]>([])
const datasources = ref<DatasourceRecord[]>([])
const resourceId = ref('')
const resourceVersion = ref('')
const loading = ref(false)
const binding = ref(false)
const error = ref('')
const status = ref('')
let resourceSeq = 0
let versionSeq = 0
let datasourceSeq = 0

const sourceKey = computed<'sql' | 'script'>(() => props.kind === 'sql' ? 'sql' : 'script')
const variableContext = computed(() => ({
  projectId: props.projectId,
  workflowId: props.workflowId,
  workflowVersion: props.workflowVersion,
  taskId: props.taskId,
}))
const inlineValue = computed(() => String(props.modelValue[sourceKey.value] ?? ''))
const accept = computed(() => ({ sql: '.sql', python: '.py', shell: '.sh' })[props.kind])

function paramsWithoutResourceRef(): Record<string, unknown> {
  const { resourceRef: _resourceRef, ...rest } = currentParams.value
  return rest
}

function emitValue(value: Record<string, unknown>) {
  currentParams.value = value
  emit('update:modelValue', value)
}

function updateInline(value: string) {
  emitValue({
    ...paramsWithoutResourceRef(),
    sourceMode: 'inline',
    [sourceKey.value]: value,
  })
}

function changeMode() {
  error.value = ''
  status.value = ''
  if (mode.value === 'inline') {
    emitValue({ ...paramsWithoutResourceRef(), sourceMode: 'inline' })
  } else {
    emitValue({ ...currentParams.value, sourceMode: 'resource' })
  }
}

async function loadDatasources() {
  if (props.kind !== 'sql') {
    datasources.value = []
    return
  }
  const seq = ++datasourceSeq
  try {
    const page = await createDatasourceContract(props.projectId).listDatasources()
    if (seq === datasourceSeq) datasources.value = page.items
  } catch (cause) {
    if (seq === datasourceSeq) error.value = cause instanceof Error ? cause.message : '数据源加载失败'
  }
}

function updateParam(key: string, value: unknown) {
  const next = { ...currentParams.value }
  if (value === '') delete next[key]
  else next[key] = value
  error.value = ''
  status.value = '已更新执行参数'
  emitValue(next)
}

function onDatasource(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  updateParam('datasource', value ? Number(value) : '')
}

function envText(): string {
  const env = currentParams.value.env
  if (!env || typeof env !== 'object' || Array.isArray(env)) return ''
  return Object.entries(env as Record<string, unknown>).map(([key, value]) => `${key}=${String(value)}`).join('\n')
}

function updateEnv(text: string) {
  const env: Record<string, string> = {}
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line) continue
    const separator = line.indexOf('=')
    if (separator <= 0 || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(line.slice(0, separator).trim())) {
      error.value = '环境变量必须使用 KEY=VALUE 格式'
      status.value = ''
      return
    }
    env[line.slice(0, separator).trim()] = line.slice(separator + 1)
  }
  updateParam('env', Object.keys(env).length ? env : '')
}

async function loadResources() {
  const seq = ++resourceSeq
  versionSeq += 1
  resources.value = []
  versions.value = []
  resourceId.value = ''
  resourceVersion.value = ''
  loading.value = true
  error.value = ''
  try {
    const items = await api.listResources(props.projectId, props.kind)
    if (seq !== resourceSeq) return
    resources.value = items
  } catch (cause) {
    if (seq === resourceSeq) error.value = cause instanceof Error ? cause.message : '资源加载失败'
  } finally {
    if (seq === resourceSeq) loading.value = false
  }
}

async function loadVersions() {
  const seq = ++versionSeq
  versions.value = []
  resourceVersion.value = ''
  const id = Number(resourceId.value)
  if (!Number.isInteger(id) || id <= 0) return false
  loading.value = true
  error.value = ''
  try {
    const items = await api.listResourceVersions(id, props.projectId)
    if (seq !== versionSeq || Number(resourceId.value) !== id) return false
    versions.value = items
    return true
  } catch (cause) {
    if (seq === versionSeq) error.value = cause instanceof Error ? cause.message : '资源版本加载失败'
    return false
  } finally {
    if (seq === versionSeq) loading.value = false
  }
}

async function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const diagnostics = validateUploadDraft(props.kind, file.name, file.size)
  if (diagnostics.length > 0) {
    error.value = diagnostics.map((item) => item.message).join('; ')
    input.value = ''
    return
  }
  loading.value = true
  error.value = ''
  status.value = ''
  try {
    const bytes = new Uint8Array(await file.arrayBuffer())
    let binary = ''
    for (const byte of bytes) binary += String.fromCharCode(byte)
    const uploaded = await api.uploadResource({
      projectId: props.projectId,
      kind: props.kind,
      filename: file.name,
      sizeBytes: file.size,
      contentBase64: btoa(binary),
    })
    resources.value = await api.listResources(props.projectId, props.kind)
    resourceId.value = String(uploaded.resourceId)
    versions.value = await api.listResourceVersions(uploaded.resourceId, props.projectId)
    resourceVersion.value = String(uploaded.version)
    status.value = `已上传 ${file.name} v${uploaded.version}，请确认绑定`
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '资源上传失败'
  } finally {
    loading.value = false
    input.value = ''
  }
}

async function bindVersion() {
  const id = Number(resourceId.value)
  const version = Number(resourceVersion.value)
  if (!Number.isInteger(id) || id <= 0 || !Number.isInteger(version) || version <= 0) {
    error.value = '请选择资源和明确版本'
    return
  }
  binding.value = true
  error.value = ''
  status.value = ''
  try {
    await api.bindResourceVersion({
      projectId: props.projectId,
      workflowId: props.workflowId,
      workflowVersion: props.workflowVersion,
      taskId: props.taskId,
      resourceId: id,
      resourceVersion: version,
    })
    emitValue({
      ...currentParams.value,
      sourceMode: 'resource',
      resourceRef: { resourceId: id, version },
    })
    status.value = `已绑定资源 ${id} 的 v${version}`
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '资源绑定失败'
  } finally {
    binding.value = false
  }
}

function hydrateSelection() {
  const refValue = props.modelValue.resourceRef
  if (!refValue || typeof refValue !== 'object') return
  const candidate = refValue as { resourceId?: unknown; version?: unknown }
  const id = Number(candidate.resourceId)
  const version = Number(candidate.version)
  if (!Number.isInteger(id) || id <= 0 || !Number.isInteger(version) || version <= 0) return
  resourceId.value = String(id)
  void loadVersions().then((applied) => { if (applied) resourceVersion.value = String(version) })
}

watch(() => [props.projectId, props.kind] as const, () => {
  void loadResources()
  void loadDatasources()
})
watch(() => props.modelValue, (value) => { currentParams.value = { ...value } }, { deep: true })
watch(() => props.modelValue.sourceMode, (value) => { mode.value = value === 'resource' ? 'resource' : 'inline' })
watch(() => props.modelValue.resourceRef, () => hydrateSelection(), { deep: true })
onMounted(async () => {
  await Promise.all([loadResources(), loadDatasources()])
  hydrateSelection()
})
</script>

<template>
  <div class="script-resource-editor" data-script-resource-editor>
    <label class="mode-field">代码来源
      <select v-model="mode" data-source-mode @change="changeMode">
        <option value="inline">内联代码</option>
        <option value="resource">版本化资源</option>
      </select>
    </label>

    <VariableReferenceInput
      v-if="mode === 'inline'"
      :model-value="inlineValue"
      :context="variableContext"
      :label="sourceKey"
      :multiline="true"
      @update:model-value="updateInline"
    />

    <div v-if="kind === 'sql'" class="execution-fields" data-sql-execution-fields>
      <label>数据源
        <select data-sql-datasource :value="String(currentParams.datasource ?? '')" @change="onDatasource">
          <option value="">使用执行环境默认数据源</option>
          <option v-for="item in datasources" :key="item.id" :value="String(item.id)">{{ item.name }} · {{ item.kind }}</option>
        </select>
      </label>
      <VariableReferenceInput data-sql-pre data-variable-field="sql-pre" :model-value="String(currentParams.pre ?? '')" :context="variableContext" label="前置 SQL" :multiline="true" @update:model-value="updateParam('pre', $event)" />
      <VariableReferenceInput data-sql-post data-variable-field="sql-post" :model-value="String(currentParams.post ?? '')" :context="variableContext" label="后置 SQL" :multiline="true" @update:model-value="updateParam('post', $event)" />
    </div>

    <div v-if="kind === 'python' || kind === 'shell'" class="execution-fields" data-script-execution-fields>
      <VariableReferenceInput v-if="kind === 'python'" data-python-requirements data-variable-field="python-requirements" :model-value="String(currentParams.requirements ?? '')" :context="variableContext" label="Python 依赖（每行一个 requirement）" :multiline="true" @update:model-value="updateParam('requirements', $event)" />
      <VariableReferenceInput data-script-env data-variable-field="script-env" :model-value="envText()" :context="variableContext" label="环境变量（每行 KEY=VALUE）" :multiline="true" @update:model-value="updateEnv" />
    </div>

    <div v-if="mode === 'resource'" class="resource-fields">
      <label>资源
        <select v-model="resourceId" data-resource-select :disabled="loading" @change="loadVersions">
          <option value="">请选择资源</option>
          <option v-for="item in resources" :key="item.resourceId" :value="String(item.resourceId)">
            {{ item.name }}（最新 v{{ item.latestVersion }}）
          </option>
        </select>
      </label>
      <label>明确版本
        <select v-model="resourceVersion" data-version-select :disabled="loading || !resourceId">
          <option value="">请选择版本</option>
          <option v-for="item in versions" :key="item.version" :value="String(item.version)">v{{ item.version }} · {{ item.digest }}</option>
        </select>
      </label>
      <label class="upload-field">上传新资源
        <input data-resource-upload type="file" :accept="accept" :disabled="loading" @change="onFile" />
      </label>
      <button type="button" class="wf-btn" data-bind-resource :disabled="binding || loading" @click="bindVersion">
        {{ binding ? '绑定中…' : '应用并绑定版本' }}
      </button>
    </div>
    <p v-if="error" class="resource-error" role="alert">{{ error }}</p>
    <p v-else-if="status" class="resource-status" role="status">{{ status }}</p>
  </div>
</template>

<style scoped>
.script-resource-editor{display:grid;gap:8px}.mode-field,.resource-fields label,.execution-fields label{display:grid;gap:3px;font-size:11px;color:var(--text-secondary,#64748b)}
.mode-field{max-width:220px}.resource-fields{display:grid;grid-template-columns:repeat(2,minmax(180px,1fr));gap:8px;align-items:end}
.resource-fields select,.mode-field select,.execution-fields select,.execution-fields textarea{border:1px solid var(--border-color,#cbd5e1);border-radius:4px;padding:5px 7px;background:#fff;font-size:12px}
.execution-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}.execution-fields textarea{resize:vertical;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
.upload-field{grid-column:1/2}.resource-error,.resource-status{margin:0;font-size:12px}.resource-error{color:#b91c1c}.resource-status{color:#15803d}
</style>

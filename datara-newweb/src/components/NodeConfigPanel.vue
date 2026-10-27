<script setup lang="ts">
/**
 * L12-02（WBS 12.2）：节点配置面板——承接选中 SYNC 组件节点的 params 配置。
 *
 * 壳范式锚：ScheduleDialog/DetailDrawer 手工表单（原生 input/select/checkbox）——
 * 禁 el-dialog/el-* 组件（vitest happy-dom 无 ElementPlus 插件，未解析组件不可测）。
 *
 * 表单契约（ENDPOINT_SELECT_SPEC，datara-backend/scripts/apply_m_b1_drafts.py L32-243）：
 *  - endpoint_select 16 params 键 + conditions 显隐 9 条（baseMode 三分型：
 *    src_base / tgt_base / file_sync）+ constraints requiredIf 2 条（requiredIf
 *    在本面板等价为可见即必填：srcTable 仅 src_base 可见、tgtTable 仅 tgt_base 必选）；
 *  - srcDs/tgtDs 下拉 = createDatasourceContract(projectId).listDatasources()
 *    的 DatasourceRecord.name（加载失败静默降级：面板提示、不阻断保存其余字段）；
 *  - 表选择器（schema.table 下拉）依赖 objects 端点，本票以文本输入承接（预研定案）；
 *  - 保存：校验可见必填 → emit('save', params)（只携带可见字段 + component 标识）
 *    → 宿主 graphStore.updateNode（R-25 diff 承接持久化，本组件不直接调 API）。
 * 非 endpoint_select 的 SYNC 组件节点走 params JSON 编辑兜底；START/END 等无
 * component 键的节点只读展示。
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import type { WorkflowDraftNode } from '../services/rebuild/workflowApi'
import { createDatasourceContract } from '../services/rebuild/datasourceApi'
import VariableReferenceInput from './VariableReferenceInput.vue'

const props = defineProps<{ node: WorkflowDraftNode; projectId: number; workflowId?: number; workflowVersion?: number }>()
const emit = defineEmits<{
  (e: 'save', params: Record<string, unknown>): void
  (e: 'close'): void
}>()

/* ---------- 节点分型 ---------- */

function paramsObject(): Record<string, unknown> {
  const p = props.node.params
  return p && typeof p === 'object' && !Array.isArray(p) ? (p as Record<string, unknown>) : {}
}

const componentType = computed(() => {
  const c = paramsObject().component
  return typeof c === 'string' ? c : ''
})
const isEndpointSelect = computed(() => componentType.value === 'endpoint_select')
const variableContext = computed(() => ({
  projectId: props.projectId,
  ...(props.workflowId !== undefined ? { workflowId: props.workflowId } : {}),
  ...(props.workflowVersion !== undefined ? { workflowVersion: props.workflowVersion } : {}),
  taskId: props.node.nodeCode,
}))
/** SYNC 组件节点（带 component 键）才有配置面；START/END/普通类型只读 */
const isSyncComponent = computed(() => componentType.value !== '')

/* ---------- endpoint_select 结构化表单（扁平契约，spec 逐键镜像） ---------- */

interface FieldDef {
  key: string
  label: string
  type: 'select' | 'text' | 'number' | 'bool' | 'ds'
  options?: { value: string; label: string }[]
  placeholder?: string
  group?: string
  /** initForm 兜底默认值（spec default 镜像；bool 缺省 false、number 缺省 0） */
  default?: string | number | boolean
  /** spec required: true（仅可见时校验；requiredIf 由 fieldVisible 分支天然承载） */
  required?: boolean
}

const EP_FIELDS: FieldDef[] = [
  {
    key: 'baseMode',
    label: '基准类型',
    type: 'select',
    default: 'src_base',
    options: [
      { value: 'src_base', label: '源表基准（源端选表）' },
      { value: 'tgt_base', label: '目标表基准（目标端选表，源端探测）' },
      { value: 'file_sync', label: '文件同步（文件源）' },
    ],
  },
  { key: 'srcDs', label: '源数据源', type: 'ds', group: '源端', required: true },
  { key: 'srcTable', label: '源表', type: 'text', group: '源端', placeholder: '如 schema.table', required: true },
  { key: 'probe', label: '联动探测匹配表', type: 'bool', group: '探测', default: false },
  {
    key: 'matchType',
    label: '匹配规则',
    type: 'select',
    group: '探测',
    default: 'exact',
    options: [
      { value: 'exact', label: '完全同名' },
      { value: 'prefix', label: '前部分命名相同' },
    ],
  },
  { key: 'matchPrefix', label: '匹配前缀', type: 'text', group: '探测', placeholder: '如 ods_order' },
  { key: 'probeResult', label: '参与 schema/表', type: 'text', group: '探测', placeholder: '逗号分隔，留空 = 探测全部' },
  { key: 'filePath', label: '文件路径', type: 'text', group: '文件源', placeholder: '如 samples/orders.csv', required: true },
  {
    key: 'fileType',
    label: '文件类型',
    type: 'select',
    group: '文件源',
    default: 'csv',
    options: [
      { value: 'csv', label: 'CSV' },
      { value: 'txt', label: 'TXT' },
      { value: 'excel', label: 'Excel' },
    ],
  },
  { key: 'fileDelimiter', label: '分隔符', type: 'text', group: '文件源', default: ',' },
  {
    key: 'fileEncoding',
    label: '编码',
    type: 'select',
    group: '文件源',
    default: 'utf-8',
    options: [
      { value: 'utf-8', label: 'UTF-8' },
      { value: 'gbk', label: 'GBK' },
      { value: 'gb18030', label: 'GB18030' },
    ],
  },
  { key: 'fileHeaderRows', label: '表头行数', type: 'number', group: '文件源', default: 1 },
  { key: 'fileSheet', label: 'Sheet 名称', type: 'text', group: '文件源', placeholder: '留空 = 首个' },
  { key: 'tgtDs', label: '目标数据源', type: 'ds', group: '目标端', required: true },
  { key: 'tgtTable', label: '目标表', type: 'text', group: '目标端', placeholder: '如 schema.table' },
  { key: 'autoCreate', label: '目标表不存在则新建', type: 'bool', group: '目标端', default: true },
]

const form = reactive<Record<string, string | number | boolean>>({})
const datasources = ref<{ name: string }[]>([])
const dsFailed = ref(false)

async function loadDatasources(): Promise<void> {
  try {
    const r = await createDatasourceContract(props.projectId).listDatasources()
    datasources.value = r.items.map((d) => ({ name: d.name }))
    dsFailed.value = false
  } catch {
    dsFailed.value = true
  }
}

/** conditions 9 条显隐映射（spec c-src-ds ~ c-file-xls 逐条镜像） */
function fieldVisible(key: string): boolean {
  const bm = String(form.baseMode ?? 'src_base')
  switch (key) {
    case 'srcDs':
      return bm !== 'file_sync'
    case 'srcTable':
      return bm === 'src_base'
    case 'probe':
    case 'matchType':
    case 'probeResult':
      return bm === 'tgt_base'
    case 'matchPrefix':
      return bm === 'tgt_base' && form.matchType === 'prefix'
    case 'filePath':
    case 'fileType':
    case 'fileHeaderRows':
      return bm === 'file_sync'
    case 'fileDelimiter':
    case 'fileEncoding':
      return bm === 'file_sync' && form.fileType !== 'excel'
    case 'fileSheet':
      return bm === 'file_sync' && form.fileType === 'excel'
    default:
      return true // tgtDs / tgtTable / autoCreate 无条件
  }
}

function initForm(): void {
  const obj = paramsObject()
  for (const f of EP_FIELDS) {
    const v = obj[f.key]
    if (f.type === 'bool') form[f.key] = typeof v === 'boolean' ? v : (f.default ?? false)
    else if (f.type === 'number') form[f.key] = typeof v === 'number' ? v : (f.default ?? 0)
    else form[f.key] = typeof v === 'string' || typeof v === 'number' ? String(v) : String(f.default ?? '')
  }
}

/* ---------- JSON 兜底（非 endpoint_select 的 SYNC 组件节点） ---------- */

const jsonText = ref('{}')

/* 面板实例化：换选中节点 / 组件分型时重建表单与 JSON 文本（编辑中不重置） */
watch(
  () => [props.node.nodeCode, componentType.value] as const,
  () => {
    if (isEndpointSelect.value) {
      initForm()
      void loadDatasources()
    } else if (isSyncComponent.value) {
      const { component: _component, ...rest } = paramsObject()
      jsonText.value = JSON.stringify(rest, null, 2)
    }
  },
  { immediate: true },
)

/* ---------- 保存 ---------- */

function validateEndpointSelect(): string | null {
  if (fieldVisible('fileHeaderRows')) {
    const headerRows = Number(form.fileHeaderRows)
    if (!Number.isInteger(headerRows)) return '表头行数必须是整数'
    if (headerRows < 0) return '表头行数不能小于 0'
  }
  for (const f of EP_FIELDS) {
    if (f.type === 'bool' || !fieldVisible(f.key)) continue
    const required = f.required === true || (f.key === 'tgtTable' && form.baseMode === 'tgt_base')
    if (required && !String(form[f.key] ?? '').trim()) {
      if (f.key === 'tgtTable') return '目标表基准：目标表必选'
      if (f.key === 'srcTable') return '源表基准：源表必选'
      return `${f.label}必填`
    }
  }
  return null
}

function onSave(): void {
  if (isEndpointSelect.value) {
    const err = validateEndpointSelect()
    if (err) {
      ElMessage.warning(err)
      return
    }
    const params: Record<string, unknown> = { component: 'endpoint_select' }
    for (const f of EP_FIELDS) {
      if (f.type === 'bool') {
        if (fieldVisible(f.key)) params[f.key] = Boolean(form[f.key])
        continue
      }
      if (!fieldVisible(f.key)) continue
      const v = form[f.key]
      if (v === '' || v === undefined) continue
      params[f.key] = f.type === 'number' ? Number(v) : v
    }
    emit('save', params)
    return
  }
  // JSON 兜底：解析校验（必须对象）→ component 标识 + 用户键
  let parsed: unknown
  try {
    parsed = JSON.parse(jsonText.value === '' ? '{}' : jsonText.value)
  } catch {
    ElMessage.warning('params 不是合法 JSON')
    return
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    ElMessage.warning('params 需为 JSON 对象（{"键": 值}）')
    return
  }
  emit('save', { ...(parsed as Record<string, unknown>), component: componentType.value })
}
</script>

<template>
  <section class="ncp" data-testid="node-config-panel">
    <header class="ncp-head">
      <span class="ncp-title" data-testid="ncp-title">{{ node.nodeCode }} · {{ node.nodeType }}</span>
      <button class="ncp-close" data-testid="ncp-close" title="关闭" @click="emit('close')">✕</button>
    </header>

    <!-- START/END 等无 component 键：只读 -->
    <p v-if="!isSyncComponent" class="ncp-hint" data-testid="ncp-readonly">
      {{ node.nodeType }} 节点无可配置参数（组件配置面仅承接 SYNC 组件节点）。
    </p>

    <!-- endpoint_select 结构化表单（扁平契约） -->
    <template v-else-if="isEndpointSelect">
      <p v-if="dsFailed" class="ncp-hint ncp-warn" data-testid="ncp-ds-failed">
        数据源列表加载失败（下拉为空，关闭重开面板可重试）。
      </p>
      <div
        v-for="f in EP_FIELDS"
        :key="f.key"
        v-show="fieldVisible(f.key)"
        class="ncp-field"
        :data-field="f.key"
      >
        <label v-if="f.type !== 'bool'" class="ncp-label">{{ f.label }}</label>
        <select
          v-if="f.type === 'select'"
          v-model="form[f.key]"
          class="ncp-input"
          :data-testid="`ncp-${f.key}`"
        >
          <option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <select
          v-else-if="f.type === 'ds'"
          v-model="form[f.key]"
          class="ncp-input"
          :data-testid="`ncp-${f.key}`"
        >
          <option value="" disabled>选择数据源</option>
          <option v-for="d in datasources" :key="d.name" :value="d.name">{{ d.name }}</option>
        </select>
        <label v-else-if="f.type === 'bool'" class="ncp-check">
          <input type="checkbox" v-model="form[f.key]" :data-testid="`ncp-${f.key}`" />
          <span>{{ f.label }}</span>
        </label>
        <VariableReferenceInput
          v-else-if="f.type === 'text'"
          :data-variable-field="`ncp-${f.key}`"
          :model-value="String(form[f.key] ?? '')"
          :context="variableContext"
          :label="f.label"
          @update:model-value="form[f.key] = $event"
        />
        <input
          v-else
          v-model="form[f.key]"
          class="ncp-input"
          type="number"
          :min="0"
          :step="1"
          :placeholder="f.placeholder"
          :data-testid="`ncp-${f.key}`"
        />
      </div>
    </template>

    <!-- 其他 SYNC 组件：params JSON 兜底 -->
    <template v-else>
      <p class="ncp-hint">组件 {{ componentType }} 结构化表单待规格下发，暂以 params JSON 编辑。</p>
      <VariableReferenceInput
        data-testid="ncp-json"
        data-variable-field="ncp-json"
        :model-value="jsonText"
        :context="variableContext"
        label="params JSON"
        :multiline="true"
        @update:model-value="jsonText = $event"
      />
    </template>

    <footer v-if="isSyncComponent" class="ncp-foot">
      <button class="ncp-btn primary" data-testid="ncp-save" @click="onSave">保存配置</button>
    </footer>
  </section>
</template>

<style scoped>
.ncp {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 12.5px;
  color: var(--text-primary, #1e293b);
}
.ncp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ncp-title {
  font-weight: 600;
  font-size: 13px;
}
.ncp-close {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary, #64748b);
  padding: 2px 6px;
}
.ncp-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.ncp-label {
  font-size: 11.5px;
  color: var(--text-secondary, #64748b);
}
.ncp-input {
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 12px;
  outline: none;
  background: #fff;
  color: var(--text-primary, #1e293b);
  font-family: inherit;
}
.ncp-input:focus {
  border-color: var(--primary-color, #2563eb);
}
.ncp-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  cursor: pointer;
  color: var(--text-primary, #1e293b);
}
.ncp-hint {
  font-size: 11.5px;
  color: var(--text-3, #94a3b8);
  margin: 0;
  line-height: 1.6;
}
.ncp-warn {
  color: var(--warning, #d97706);
}
.ncp-foot {
  display: flex;
  justify-content: flex-end;
  padding-top: 4px;
  border-top: 1px solid var(--border-color, #e2e8f0);
}
.ncp-btn {
  border: 1px solid var(--border-color, #e2e8f0);
  background: #fff;
  border-radius: 6px;
  padding: 4px 14px;
  font-size: 12px;
  cursor: pointer;
  color: var(--text-primary, #1e293b);
}
.ncp-btn.primary {
  border-color: var(--primary-color, #2563eb);
  background: var(--primary-color, #2563eb);
  color: #fff;
}
</style>

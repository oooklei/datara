<script setup lang="ts">
import { computed, ref, watch, type CSSProperties } from 'vue'
import {
  createVariableContract,
  type VariableDefinition,
  type VariableScope,
  type VariableValueType,
} from '../../services/rebuild/variableApi'
import { useDraggable } from '../../composables/useDraggable'

const props = withDefaults(defineProps<{
  modelValue: boolean
  projectId?: number
  canEdit?: boolean
}>(), { projectId: undefined, canEdit: true })
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const api = createVariableContract()
const rows = ref<VariableDefinition[]>([])
const loading = ref(false)
const error = ref('')
let loadSeq = 0
const scope = ref<Extract<VariableScope, 'global' | 'project' | 'env'>>('project')
const environmentGroupId = ref<number | undefined>()
const editing = ref(false)
const preserveExistingValue = ref(false)
const saving = ref(false)
const form = ref({ name: '', value: '', valueType: 'string' as VariableValueType, sensitive: false, description: '' })

const owner = computed(() => scope.value === 'env' && environmentGroupId.value
  ? { environmentGroupId: environmentGroupId.value }
  : {})

/* D9：变量管理抽屉可由标题栏拖动；CSS 为 inset:56px 0 0 auto（top/right/bottom 三锚），
   拖拽定位后解除 right/bottom 约束并按 top 反推高度，避免抽屉被压缩或溢出视口。 */
const drawerRef = ref<HTMLElement | null>(null)
const headerRef = ref<HTMLElement | null>(null)
const { dragStyle: drawerDragStyle, onHandlePointerdown } = useDraggable(drawerRef, headerRef, { storageKey: 'variables.drawer' })
const drawerStyle = computed<CSSProperties>(() => {
  const base = drawerDragStyle.value
  if (!base.position) return base
  return { ...base, right: 'auto', bottom: 'auto', height: `calc(100vh - ${base.top})` }
})

async function load() {
  const seq = ++loadSeq
  rows.value = []
  error.value = ''
  if (!props.modelValue || props.projectId === undefined) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const items = await api.listVariables(
      props.projectId,
      ['global', 'project', 'env'],
      environmentGroupId.value ? { environmentGroupId: environmentGroupId.value } : {},
    )
    if (seq === loadSeq) rows.value = items
  } catch {
    if (seq === loadSeq) error.value = '变量加载失败，请重试'
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function beginCreate() {
  form.value = { name: '', value: '', valueType: 'string', sensitive: false, description: '' }
  preserveExistingValue.value = false
  editing.value = true
}

function beginEdit(row: VariableDefinition) {
  scope.value = row.scope as typeof scope.value
  form.value = {
    name: row.name,
    value: row.sensitive ? '' : (row.value ?? ''),
    valueType: row.valueType,
    sensitive: !!row.sensitive,
    description: row.description ?? '',
  }
  preserveExistingValue.value = !!row.sensitive
  editing.value = true
}

async function save() {
  if (props.projectId === undefined || !form.value.name.trim() || (!form.value.value && !(editing.value && form.value.sensitive))) return
  saving.value = true
  error.value = ''
  try {
    const definition: VariableDefinition = {
      scope: scope.value,
      ...form.value,
      ...owner.value,
    }
    if (preserveExistingValue.value && definition.sensitive && definition.value === '') {
      delete definition.value
    }
    await api.saveVariable(props.projectId, definition)
    editing.value = false
    await load()
  } catch {
    error.value = '变量保存失败，请检查名称、类型和值'
  } finally {
    saving.value = false
  }
}

async function remove(row: VariableDefinition) {
  if (props.projectId === undefined || !props.canEdit) return
  error.value = ''
  try {
    await api.deleteVariable(props.projectId, row.scope, row.name, {
      environmentGroupId: row.environmentGroupId,
      workflowId: row.workflowId,
      taskId: row.taskId,
    })
    await load()
  } catch {
    error.value = '变量删除失败'
  }
}

watch(() => [props.modelValue, props.projectId], load, { immediate: true })
</script>

<template>
  <aside v-if="modelValue" ref="drawerRef" class="variable-drawer" aria-label="变量管理" data-variable-manager :style="drawerStyle">
    <header ref="headerRef" class="drag-handle" @pointerdown="onHandlePointerdown">
      <div><h2>变量管理</h2><p>全局、项目与环境组变量</p></div>
      <button type="button" aria-label="关闭变量管理" @pointerdown.stop @click="emit('update:modelValue', false)">×</button>
    </header>
    <div class="toolbar">
      <button data-variable-create type="button" :disabled="!canEdit || projectId === undefined" @click="beginCreate">新建变量</button>
      <button data-variable-retry type="button" @click="load">刷新</button>
      <label>环境组 ID <input v-model.number="environmentGroupId" data-environment-group type="number" min="1" @change="load" /></label>
    </div>
    <p v-if="!canEdit" class="notice" data-variable-permission>当前角色仅可查看变量</p>
    <p v-if="loading" data-variable-loading>正在加载变量…</p>
    <div v-else-if="error" class="error" data-variable-error>{{ error }}</div>
    <p v-else-if="rows.length === 0" data-variable-empty>暂无变量</p>
    <table v-else>
      <thead><tr><th>作用域</th><th>名称</th><th>类型</th><th>当前值</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="row in rows" :key="`${row.scope}:${row.name}`">
          <td>{{ row.scope }}</td><td>{{ row.name }}</td><td>{{ row.valueType }}</td>
          <td>{{ row.sensitive ? '******' : row.value }}</td>
          <td><button :disabled="!canEdit" @click="beginEdit(row)">编辑</button><button :disabled="!canEdit" @click="remove(row)">删除</button></td>
        </tr>
      </tbody>
    </table>
    <form v-if="editing" class="editor" @submit.prevent="save">
      <label>作用域<select v-model="scope"><option value="global">全局</option><option value="project">项目</option><option value="env">环境组</option></select></label>
      <label v-if="scope === 'env'">环境组 ID<input v-model.number="environmentGroupId" type="number" min="1" required /></label>
      <label>名称<input v-model="form.name" data-variable-name required /></label>
      <label>类型<select v-model="form.valueType"><option v-for="item in ['string','integer','decimal','boolean','date','datetime','json','array']" :key="item">{{ item }}</option></select></label>
      <!-- Sensitive values are write-only.  When editing an existing secret the
           server must receive an empty value to keep the current secret; a
           blanket `required` here prevented that valid update path. -->
      <label>值<input v-model="form.value" data-variable-value :type="form.sensitive ? 'password' : 'text'" :required="!form.sensitive || !editing" :placeholder="form.sensitive && editing ? '留空表示保持原值' : ''" /></label>
      <label><input v-model="form.sensitive" type="checkbox" />敏感值</label>
      <label>描述<input v-model="form.description" /></label>
      <div><button data-variable-save type="submit" :disabled="saving">保存</button><button type="button" @click="editing = false">取消</button></div>
    </form>
  </aside>
</template>

<style scoped>
.variable-drawer{position:fixed;z-index:2000;inset:56px 0 0 auto;width:min(720px,94vw);background:var(--card);border-left:1px solid var(--border-strong);box-shadow:-12px 0 32px color-mix(in srgb, var(--text) 12%, transparent);padding:18px;overflow:auto}
header,.toolbar,header>div,.editor>div{display:flex;align-items:center;justify-content:space-between;gap:12px}h2,p{margin:0}.toolbar{justify-content:flex-start;margin:16px 0}.notice{padding:8px;background:var(--bg)}.error{color:var(--danger);padding:12px;background:var(--danger-bg)}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--border)}.editor{margin-top:18px;padding:14px;background:var(--bg);display:grid;gap:10px}.editor label{display:grid;gap:4px}input,select,button{font:inherit;padding:6px 9px}.drag-handle{cursor:grab;user-select:none}.drag-handle:active{cursor:grabbing}
</style>

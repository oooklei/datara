<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  createVariableContract,
  type VariableDefinition,
  type VariableScope,
  type VariableValueType,
} from '../../services/rebuild/variableApi'

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
const scope = ref<Extract<VariableScope, 'global' | 'project' | 'env'>>('project')
const environmentGroupId = ref<number | undefined>()
const editing = ref(false)
const saving = ref(false)
const form = ref({ name: '', value: '', valueType: 'string' as VariableValueType, sensitive: false, description: '' })

const owner = computed(() => scope.value === 'env' && environmentGroupId.value
  ? { environmentGroupId: environmentGroupId.value }
  : {})

async function load() {
  if (!props.modelValue || props.projectId === undefined) return
  loading.value = true
  error.value = ''
  try {
    rows.value = await api.listVariables(
      props.projectId,
      ['global', 'project', 'env'],
      environmentGroupId.value ? { environmentGroupId: environmentGroupId.value } : {},
    )
  } catch {
    error.value = '变量加载失败，请重试'
  } finally {
    loading.value = false
  }
}

function beginCreate() {
  form.value = { name: '', value: '', valueType: 'string', sensitive: false, description: '' }
  editing.value = true
}

function beginEdit(row: VariableDefinition) {
  scope.value = row.scope as typeof scope.value
  form.value = {
    name: row.name,
    value: row.sensitive ? '' : row.value,
    valueType: row.valueType,
    sensitive: !!row.sensitive,
    description: row.description ?? '',
  }
  editing.value = true
}

async function save() {
  if (props.projectId === undefined || !form.value.name.trim() || !form.value.value) return
  saving.value = true
  error.value = ''
  try {
    await api.saveVariable(props.projectId, {
      scope: scope.value,
      ...form.value,
      ...owner.value,
    })
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
  <aside v-if="modelValue" class="variable-drawer" aria-label="变量管理" data-variable-manager>
    <header>
      <div><h2>变量管理</h2><p>全局、项目与环境组变量</p></div>
      <button type="button" aria-label="关闭变量管理" @click="emit('update:modelValue', false)">×</button>
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
      <label>值<input v-model="form.value" data-variable-value :type="form.sensitive ? 'password' : 'text'" required /></label>
      <label><input v-model="form.sensitive" type="checkbox" />敏感值</label>
      <label>描述<input v-model="form.description" /></label>
      <div><button data-variable-save type="submit" :disabled="saving">保存</button><button type="button" @click="editing = false">取消</button></div>
    </form>
  </aside>
</template>

<style scoped>
.variable-drawer{position:fixed;z-index:2000;inset:56px 0 0 auto;width:min(720px,94vw);background:#fff;border-left:1px solid #dbe3ef;box-shadow:-12px 0 32px #0f172a1f;padding:18px;overflow:auto}
header,.toolbar,header>div,.editor>div{display:flex;align-items:center;justify-content:space-between;gap:12px}h2,p{margin:0}.toolbar{justify-content:flex-start;margin:16px 0}.notice{padding:8px;background:#f8fafc}.error{color:#b91c1c;padding:12px;background:#fef2f2}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px;border-bottom:1px solid #e2e8f0}.editor{margin-top:18px;padding:14px;background:#f8fafc;display:grid;gap:10px}.editor label{display:grid;gap:4px}input,select,button{font:inherit;padding:6px 9px}
</style>

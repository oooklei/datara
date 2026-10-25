<script setup lang="ts">
/**
 * 变量管理管理面（L5-02；§5A.5 入口=任务中心主页面按钮布局；§5B 细化设计）：
 * - 分层承载（§5A.5）：全局/项目变量=本管理面；工作流级/临时变量=DAG 画布「变量」页签；实例变量与时间戳=run-snapshot 透传；
 * - 功能域：list + upsert 保存（saveVariable 为 upsert 语义，同 scope+name 覆盖）；后端六端点无 DELETE，本面不提供删除（缺口已登记候裁）；
 * - 七级 namespace 选择器 run > task > workflow > project > global > env > builtin 全展示不收窄（票面退出标准）；
 *   run/env/builtin 不可持久化（后端 PERSISTABLE_SCOPES → 4001），tmp/workflow/task 归画布变量面板——本面可保存域=global/project；
 * - 类型：八值 VariableValueType 全集（修正验证页四值下拉与真源不一致缺陷）；
 * - 值位=变量引用输入组件（§5B.2 全域输入位可引用 + §5B.3 校验 + §5B.4 现时值 + §5B.5 补全）。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  VARIABLE_SCOPE_PRIORITY,
  createVariableContract,
  type VariableDefinition,
  type VariableValueType,
} from '../../services/rebuild/variableApi'
import { useAuthStore } from '../../stores/auth'
import VariableRefInput from './VariableRefInput.vue'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})
const auth = useAuthStore()
const contract = createVariableContract()

/** 当前单项目演示态（sqlIdeApi / metrics 验证页同模式常量） */
const PROJECT_ID = 1

/* scope 提示矩阵：七级全展示；本面可保存域=global/project */
const SCOPE_HINT: Partial<Record<string, string>> = {
  run: '运行时作用域不可持久化存储（后端拒绝 4001）',
  env: '环境作用域由环境配置管理，不可在此保存',
  builtin: '内置作用域只读，不可在此保存',
  tmp: '临时作用域在工作流画布「变量」页签内管理',
  workflow: '工作流作用域在工作流画布「变量」页签内管理',
  task: '任务作用域在工作流画布「变量」页签内管理',
}
const saveDisabledScope = (s: string) => s !== 'global' && s !== 'project'

/* ---------- 列表 ---------- */
interface Row {
  scope: string
  name: string
  valueType: string
  value: string
  sensitive: boolean
  description: string
}
const rows = ref<Row[]>([])
const loading = ref(false)

async function loadRows() {
  loading.value = true
  try {
    const items = await contract.listVariables(PROJECT_ID, ['global', 'project'])
    rows.value = items.map((i) => ({
      scope: i.scope,
      name: i.name,
      valueType: i.valueType,
      value: i.value ?? '',
      sensitive: !!i.sensitive,
      description: i.description ?? '',
    }))
  } catch (e) {
    ElMessage.error('变量列表加载失败：' + (e instanceof Error ? e.message : String(e)))
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (on) => {
    if (!on) return
    resetForm()
    void loadRows()
  },
)

/* ---------- 表单（upsert） ---------- */
const VALUE_TYPES: VariableValueType[] = ['string', 'integer', 'decimal', 'boolean', 'date', 'datetime', 'json', 'array']
const form = ref({ scope: 'global', name: '', valueType: 'string' as VariableValueType, value: '', sensitive: false, description: '' })
const editing = ref(false)
const submitting = ref(false)

function resetForm() {
  form.value = { scope: 'global', name: '', valueType: 'string', value: '', sensitive: false, description: '' }
  editing.value = false
}

function onEditRow(r: Row) {
  form.value = {
    scope: r.scope,
    name: r.name,
    valueType: r.valueType as VariableValueType,
    value: r.value,
    sensitive: r.sensitive,
    description: r.description,
  }
  editing.value = true
}

async function submit() {
  if (!auth.canEdit) {
    ElMessage.warning('当前角色为只读，无权修改变量')
    return
  }
  const name = form.value.name.trim()
  if (!name) {
    ElMessage.warning('变量名不能为空')
    return
  }
  if (saveDisabledScope(form.value.scope)) {
    ElMessage.warning(SCOPE_HINT[form.value.scope] ?? '该作用域不可在此保存')
    return
  }
  submitting.value = true
  try {
    const definition: VariableDefinition = {
      scope: form.value.scope as VariableDefinition['scope'],
      name,
      valueType: form.value.valueType,
      value: form.value.value,
      sensitive: form.value.sensitive,
      description: form.value.description,
    }
    await contract.saveVariable(PROJECT_ID, definition)
    ElMessage.success(`变量 ${form.value.scope}.${name} 已保存`)
    resetForm()
    await loadRows()
  } catch (e) {
    ElMessage.error('保存失败：' + (e instanceof Error ? e.message : String(e)))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="变量管理" width="860px" append-to-body destroy-on-close>
    <div class="vm" data-testid="variables-manage-dialog">
      <el-alert
        type="info"
        :closable="false"
        title="承载全局/项目变量（保存即写入，同名覆盖）；工作流级/临时变量在 DAG 画布「变量」页签管理；运行时与环境/内置作用域不可持久化。"
      />
      <el-table v-loading="loading" :data="rows" size="small" class="vm-table" data-testid="variables-table">
        <el-table-column prop="scope" label="作用域" width="90" />
        <el-table-column prop="name" label="变量名" width="160" />
        <el-table-column prop="valueType" label="类型" width="90" />
        <el-table-column label="值">
          <template #default="{ row }">{{ row.sensitive ? '●●●●●●' : row.value }}</template>
        </el-table-column>
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
        <el-table-column label="操作" width="70">
          <template #default="{ row }">
            <el-button link type="primary" size="small" data-testid="variables-edit" @click="onEditRow(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-divider content-position="left">{{ editing ? '编辑变量（同名覆盖保存）' : '新建变量' }}</el-divider>
      <el-form label-width="90px" size="small" @submit.prevent>
        <el-form-item label="作用域">
          <el-select v-model="form.scope" data-testid="variables-scope" class="vm-scope">
            <el-option
              v-for="s in VARIABLE_SCOPE_PRIORITY"
              :key="s"
              :value="s"
              :label="saveDisabledScope(s) ? `${s}（不可在此保存）` : s"
            />
          </el-select>
          <span v-if="SCOPE_HINT[form.scope]" class="vm-hint" data-testid="variables-scope-hint">{{ SCOPE_HINT[form.scope] }}</span>
        </el-form-item>
        <el-form-item label="变量名">
          <el-input v-model="form.name" data-testid="variables-name" placeholder="如 region" class="vm-name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.valueType" data-testid="variables-type" class="vm-scope">
            <el-option v-for="t in VALUE_TYPES" :key="t" :value="t" :label="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="值">
          <VariableRefInput v-model="form.value" :project-id="PROJECT_ID" class="vm-ref" />
        </el-form-item>
        <el-form-item label="敏感值">
          <el-switch v-model="form.sensitive" data-testid="variables-sensitive" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" data-testid="variables-desc" class="vm-name" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" data-testid="variables-save" @click="submit">保存</el-button>
          <el-button data-testid="variables-reset" @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </div>
  </el-dialog>
</template>

<style scoped>
.vm-table { margin-top: 10px; }
.vm-scope { width: 200px; }
.vm-name { width: 320px; }
.vm-ref { width: 100%; }
.vm-hint { margin-left: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
</style>

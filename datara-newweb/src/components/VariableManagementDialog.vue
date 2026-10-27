<!--
  变量管理管理面（L5-02 / §5A.5 入口=任务中心主页面按钮；§5B 细化设计）。
  蓝本：datara-web/src/views/variables/VariablesManageDialog.vue（L1-213，§5A.5 + §5B 同一蓝本）——
  功能域照搬：list + upsert 保存（saveVariable 为 upsert 语义，同 scope+name 覆盖）；后端六端点
  无 DELETE，本面不提供删除（缺口已登记候裁）；七级 namespace 选择器全展示不收窄（票面退出标准）；
  本面可保存域=global/project（run/env/builtin 不可持久化 → 后端 4001；tmp/workflow/task 归画布
  「变量」页签）；类型=八值 VariableValueType 全集。
  壳范式锚：ScheduleDialog.vue / LlmModelFormDialog.vue 手工模态（Teleport + 遮罩 + role=dialog），
  **禁 el-dialog/el-* 组件**——vitest happy-dom 环境未注册 ElementPlus 组件，未解析组件渲染 slot
  不受 v-if 控制不可测；故列表/表单全部原生 table/form 承载。
  CSS 变量统一走 theme.css 令牌层（对标旧前端蓝本令牌名），无 fallback 十六进制。
-->
<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  VARIABLE_SCOPE_PRIORITY,
  createVariableContract,
  type VariableDefinition,
  type VariableValueType,
} from '../services/rebuild/variableApi'

const props = defineProps<{ modelValue: boolean; projectId: number | undefined }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

/** 契约工厂无入参（projectId 逐方法传入）；本面固定查询 global/project 可持久化域。 */
const api = createVariableContract()

const VALUE_TYPES: VariableValueType[] = ['string', 'integer', 'decimal', 'boolean', 'date', 'datetime', 'json', 'array']

/** 七级全展示 + tmp（画布承载）；本面可保存域=global/project */
const SCOPE_OPTIONS: string[] = [...VARIABLE_SCOPE_PRIORITY, 'tmp']
const SCOPE_HINT: Partial<Record<string, string>> = {
  run: '运行时作用域不可持久化存储（后端拒绝 4001）',
  env: '环境作用域由环境配置管理，不可在此保存',
  builtin: '内置作用域只读，不可在此保存',
  tmp: '临时作用域在工作流画布「变量」页签内管理',
  workflow: '工作流作用域在工作流画布「变量」页签内管理',
  task: '任务作用域在工作流画布「变量」页签内管理',
}
const saveDisabledScope = (s: string) => s !== 'global' && s !== 'project'

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
const loadError = ref('')
let loadSeq = 0

async function loadRows(): Promise<void> {
  const seq = ++loadSeq
  rows.value = []
  loadError.value = ''
  if (props.projectId === undefined) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const items = await api.listVariables(props.projectId, ['global', 'project'])
    if (seq !== loadSeq) return
    rows.value = items.map((i) => ({
      scope: i.scope,
      name: i.name,
      valueType: i.valueType,
      value: i.value ?? '',
      sensitive: !!i.sensitive,
      description: i.description ?? '',
    }))
  } catch (e) {
    if (seq === loadSeq) loadError.value = '变量列表加载失败：' + (e instanceof Error ? e.message : String(e))
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

const form = reactive({
  scope: 'global',
  name: '',
  valueType: 'string' as VariableValueType,
  value: '',
  sensitive: false,
  description: '',
})
const editing = ref(false)
const submitting = ref(false)
const formError = ref('')

function resetForm(): void {
  form.scope = 'global'
  form.name = ''
  form.valueType = 'string'
  form.value = ''
  form.sensitive = false
  form.description = ''
  editing.value = false
  formError.value = ''
}

watch(
  () => [props.modelValue, props.projectId] as const,
  () => {
    if (!props.modelValue) return
    resetForm()
    void loadRows()
  },
  { immediate: true },
)

function close(): void {
  if (submitting.value) return
  visible.value = false
}

function onEditRow(r: Row): void {
  form.scope = r.scope
  form.name = r.name
  form.valueType = r.valueType as VariableValueType
  // Never round-trip the masked list value. Omitting a blank sensitive value
  // tells the backend repository to preserve the stored secret.
  form.value = r.sensitive ? '' : r.value
  form.sensitive = r.sensitive
  form.description = r.description
  editing.value = true
  formError.value = ''
}

async function submit(): Promise<void> {
  if (submitting.value) return
  if (props.projectId === undefined) {
    formError.value = '无项目上下文，变量管理待项目路由接驳'
    return
  }
  const name = form.name.trim()
  if (!name) {
    formError.value = '变量名不能为空'
    return
  }
  if (saveDisabledScope(form.scope)) {
    formError.value = SCOPE_HINT[form.scope] ?? '该作用域不可在此保存'
    return
  }
  if (!(VALUE_TYPES as readonly string[]).includes(form.valueType)) {
    formError.value = '值类型不在支持范围内'
    return
  }
  submitting.value = true
  formError.value = ''
  try {
    const definition: VariableDefinition = {
      scope: form.scope as VariableDefinition['scope'],
      name,
      valueType: form.valueType,
      sensitive: form.sensitive,
      description: form.description,
    }
    if (!(editing.value && form.sensitive && form.value === '')) {
      definition.value = form.value
    }
    await api.saveVariable(props.projectId, definition)
    ElMessage.success(`变量 ${form.scope}.${name} 已保存`)
    resetForm()
    await loadRows()
  } catch (e) {
    formError.value = '保存失败：' + (e instanceof Error ? e.message : String(e))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="vm-mask" data-testid="variables-manage-mask" @click.self="close">
      <section class="vm-panel" role="dialog" aria-modal="true" aria-label="变量管理" data-testid="variables-manage-dialog">
        <header class="vm-header">
          <span class="vm-title">变量管理</span>
          <button type="button" class="vm-close" aria-label="关闭" data-testid="variables-close" @click="close">×</button>
        </header>

        <div class="vm-body">
          <p class="vm-alert">
            承载全局/项目变量（保存即写入，同名覆盖）；工作流级/临时变量在 DAG 画布「变量」页签管理；运行时与环境/内置作用域不可持久化。
          </p>

          <p v-if="projectId === undefined" class="vm-hint" data-testid="variables-no-project">
            无项目上下文，变量管理待项目路由接驳（/dag 过渡路由无项目段）。
          </p>

          <template v-else>
            <div class="vm-toolbar">
              <button type="button" class="vm-btn vm-btn--primary" data-testid="variables-new" :disabled="editing" @click="resetForm">
                {{ editing ? '编辑中…' : '新建变量' }}
              </button>
            </div>

            <p v-if="loading" class="vm-hint" data-testid="variables-loading">加载中…</p>
            <div v-else-if="loadError" class="vm-error" role="alert" data-testid="variables-error">
              <span>{{ loadError }}</span>
              <button type="button" class="vm-btn vm-btn--primary" data-testid="variables-retry" @click="loadRows">重试</button>
            </div>
            <p v-else-if="rows.length === 0" class="vm-hint" data-testid="variables-empty">暂无全局/项目变量</p>
            <table v-else class="vm-table" data-testid="variables-table">
              <thead>
                <tr>
                  <th>作用域</th>
                  <th>变量名</th>
                  <th>类型</th>
                  <th>值</th>
                  <th>描述</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in rows" :key="`${r.scope}.${r.name}`">
                  <td>{{ r.scope }}</td>
                  <td>{{ r.name }}</td>
                  <td>{{ r.valueType }}</td>
                  <td>{{ r.sensitive ? '●●●●●●' : r.value }}</td>
                  <td>{{ r.description || '-' }}</td>
                  <td class="vm-actions">
                    <button type="button" class="vm-link" data-testid="variables-edit" @click="onEditRow(r)">编辑</button>
                  </td>
                </tr>
              </tbody>
            </table>

            <div class="vm-form-wrap">
              <p class="vm-form-title">{{ editing ? '编辑变量（同名覆盖保存）' : '新建变量' }}</p>
              <form class="vm-form" data-testid="variables-form" @submit.prevent="submit">
                <label class="vm-field">
                  <span class="vm-label">作用域</span>
                  <select v-model="form.scope" class="vm-input" data-testid="variables-scope">
                    <option v-for="s in SCOPE_OPTIONS" :key="s" :value="s">
                      {{ saveDisabledScope(s) ? `${s}（不可在此保存）` : s }}
                    </option>
                  </select>
                  <span v-if="SCOPE_HINT[form.scope]" class="vm-field-hint" data-testid="variables-scope-hint">{{ SCOPE_HINT[form.scope] }}</span>
                </label>
                <label class="vm-field">
                  <span class="vm-label">变量名</span>
                  <input v-model="form.name" class="vm-input" data-testid="variables-name" placeholder="如 region" />
                </label>
                <label class="vm-field">
                  <span class="vm-label">类型</span>
                  <select v-model="form.valueType" class="vm-input" data-testid="variables-type">
                    <option v-for="t in VALUE_TYPES" :key="t" :value="t">{{ t }}</option>
                  </select>
                </label>
                <label class="vm-field">
                  <span class="vm-label">值</span>
                  <input v-model="form.value" class="vm-input" data-testid="variables-value" placeholder="字面值或 ${scope.name} 引用" />
                </label>
                <label class="vm-field">
                  <span class="vm-label">描述</span>
                  <input v-model="form.description" class="vm-input" data-testid="variables-desc" placeholder="用途说明（可选）" />
                </label>
                <label class="vm-check">
                  <input v-model="form.sensitive" type="checkbox" data-testid="variables-sensitive" />
                  <span>敏感值（列表掩码回显）</span>
                </label>
                <p v-if="formError" class="vm-form-error" role="alert" data-testid="variables-form-error">{{ formError }}</p>
              </form>
              <footer class="vm-footer">
                <button type="button" class="vm-btn" data-testid="variables-reset" :disabled="submitting" @click="resetForm">重置</button>
                <button type="button" class="vm-btn vm-btn--primary" data-testid="variables-save" :disabled="submitting" @click="submit">
                  {{ submitting ? '提交中…' : '保存' }}
                </button>
              </footer>
            </div>
          </template>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.vm-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}
.vm-panel {
  width: 860px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 96px);
  background: var(--card);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.vm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
}
.vm-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}
.vm-close {
  border: none;
  background: none;
  font-size: 20px;
  line-height: 1;
  color: var(--text-3);
  cursor: pointer;
  padding: 0 4px;
}
.vm-body {
  padding: 16px 20px;
  overflow-y: auto;
  flex: 1;
}
.vm-alert {
  margin: 0 0 12px;
  border: 1px solid var(--info-bg);
  background: var(--info-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text-2);
}
.vm-hint {
  margin: 12px 0;
  font-size: 13px;
  color: var(--text-3);
}
.vm-toolbar {
  margin-bottom: 10px;
}
.vm-btn {
  height: 32px;
  padding: 0 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text-2);
  font-size: 13px;
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease), border-color var(--dur-fast) var(--ease);
}
.vm-btn:hover {
  color: var(--primary);
  border-color: var(--primary);
}
.vm-btn--primary {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}
.vm-btn--primary:hover {
  background: var(--primary-hover);
  border-color: var(--primary-hover);
  color: #fff;
}
.vm-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.vm-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 12px 0;
  border: 1px solid var(--danger-bg);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 12px;
  color: var(--danger);
}
.vm-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.vm-table th,
.vm-table td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
.vm-table th {
  font-size: 12px;
  color: var(--text-3);
  font-weight: 500;
}
.vm-actions {
  text-align: right;
}
.vm-link {
  border: none;
  background: none;
  color: var(--primary);
  cursor: pointer;
  font-size: 13px;
  padding: 0;
}
.vm-link:hover {
  color: var(--primary-hover);
}
.vm-form-wrap {
  margin-top: 16px;
  border-top: 1px solid var(--border);
  padding-top: 14px;
}
.vm-form-title {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.vm-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 16px;
}
.vm-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.vm-label {
  font-size: 12px;
  color: var(--text-2);
}
.vm-field-hint {
  font-size: 12px;
  color: var(--text-3);
}
.vm-input {
  height: 32px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 10px;
  font-size: 13px;
  color: var(--text);
  background: var(--card);
  box-sizing: border-box;
}
.vm-input:focus {
  outline: none;
  border-color: var(--primary);
}
.vm-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-2);
}
.vm-form-error {
  grid-column: 1 / -1;
  margin: 0;
  border: 1px solid var(--danger-bg);
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 12px;
  color: var(--danger);
}
.vm-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 14px;
}
</style>

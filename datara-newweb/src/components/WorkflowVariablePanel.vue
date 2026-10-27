<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  createVariableContract,
  VARIABLE_SCOPE_PRIORITY,
  type VariableDefinition,
  type VariableScope,
  type VariableValueType,
} from '../services/rebuild/variableApi'

// Vue 运行时对纯 Boolean prop 未传且无 default 时注入 false（实测）——必须显式默认 true，
// 否则工作台接线未传 canEdit 时保存/删除按钮恒被禁用（T7 测试暴露的存量缺陷）
const props = withDefaults(defineProps<{ modelValue: boolean; projectId: number; workflowId: number; canEdit?: boolean }>(), { canEdit: true })
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const api = createVariableContract()
const rows = ref<VariableDefinition[]>([])
const loading = ref(false)
const error = ref('')
const form = ref({ name: '', value: '', valueType: 'string' as VariableValueType, sensitive: false })

/* ---- T7 变量七级链分域（权威设计 §5B.1）----
 * 画布面板承载工作流级变量的管理面；上游域（project/env/global）只读展示，
 * 其管理面在任务中心「变量管理」抽屉，run/task/builtin 由运行实例与引擎提供。
 * 解析取七级链上首个命中域：run > task > workflow > project > env > global > builtin。
 */
const EDITABLE_SCOPES = new Set<VariableScope>(['workflow'])
const PANEL_SCOPES: VariableScope[] = ['workflow', 'project', 'env', 'global']
const SCOPE_LABELS: Record<string, string> = {
  run: '运行实例', task: '节点', workflow: '工作流', project: '项目',
  env: '环境组', global: '全局', builtin: '内置',
}
const chainScopes = VARIABLE_SCOPE_PRIORITY

const scopeGroups = computed(() => PANEL_SCOPES
  .map((scope) => ({
    scope,
    label: SCOPE_LABELS[scope] ?? scope,
    editable: EDITABLE_SCOPES.has(scope),
    items: rows.value.filter((row) => row.scope === scope),
  }))
  .filter((group) => group.items.length > 0))

/* T7 解析链预览：表达式 ${scope.name} 现值解析 + 来源域展示（表单八项能力之「现值预览/来源展示」） */
const previewExpression = ref('')
const previewing = ref(false)
const previewResult = ref('')
const previewError = ref('')

async function runPreview() {
  const expression = previewExpression.value.trim()
  if (!expression) return
  previewing.value = true
  previewError.value = ''
  previewResult.value = ''
  try {
    const result = await api.previewResolution(expression, { projectId: props.projectId, workflowId: props.workflowId })
    if (result.resolvedValue === null) {
      previewResult.value = result.diagnostics.map((item) => item.message).join('；') || '无法解析该表达式'
    } else {
      previewResult.value = `${result.resolvedValue}（来源 ${result.source ? `${result.source.scope}.${result.source.name}` : '—'}）`
    }
  } catch {
    previewError.value = '解析预览失败，请稍后重试'
  } finally {
    previewing.value = false
  }
}

async function load() {
  if (!props.modelValue) return
  loading.value = true
  error.value = ''
  try { rows.value = await api.listVariables(props.projectId, PANEL_SCOPES, { workflowId: props.workflowId }) }
  catch { error.value = '变量加载失败' }
  finally { loading.value = false }
}

async function save() {
  if (!form.value.name.trim() || !form.value.value) return
  await api.saveVariable(props.projectId, { scope: 'workflow', workflowId: props.workflowId, ...form.value })
  form.value = { name: '', value: '', valueType: 'string', sensitive: false }
  await load()
}

async function remove(row: VariableDefinition) {
  if (!EDITABLE_SCOPES.has(row.scope)) return
  await api.deleteVariable(props.projectId, row.scope, row.name, { workflowId: props.workflowId })
  await load()
}

watch(() => [props.modelValue, props.projectId, props.workflowId], load, { immediate: true })
</script>

<template>
  <section v-if="modelValue" class="workflow-variable-panel" data-workflow-variable-panel>
    <header><strong>工作流变量</strong><button @click="emit('update:modelValue', false)">关闭</button></header>
    <div class="chain" data-variable-chain aria-label="变量解析优先级链">
      <template v-for="(scope, index) in chainScopes" :key="scope">
        <span v-if="index > 0" class="chain-arrow">&gt;</span>
        <span class="chain-scope" :data-chain-scope="scope">{{ scope }}</span>
      </template>
    </div>
    <p class="hint">引用语法 <code>${scope.name}</code>；解析取链上首个命中域。工作流级在此维护，其余域由任务中心「变量管理」或运行实例提供。</p>
    <div class="preview" data-variable-preview>
      <input v-model="previewExpression" data-variable-preview-input placeholder="输入表达式，如 ${workflow.rate}" @keyup.enter="runPreview" />
      <button data-variable-preview-run type="button" :disabled="previewing" @click="runPreview">解析预览</button>
      <p v-if="previewError" class="error" data-variable-preview-error>{{ previewError }}</p>
      <p v-else-if="previewResult" data-variable-preview-result>{{ previewResult }}</p>
    </div>
    <p v-if="loading">加载中…</p><p v-else-if="error" class="error">{{ error }}</p>
    <template v-else>
      <p v-if="!scopeGroups.length" data-variable-empty>暂无变量</p>
      <section v-for="group in scopeGroups" :key="group.scope" class="scope-group" :data-scope-group="group.scope">
        <h4>{{ group.label }}（{{ group.scope }}）<small v-if="!group.editable">只读 · 去任务中心「变量管理」维护</small></h4>
        <ul><li v-for="row in group.items" :key="`${row.scope}:${row.name}`"><code>{{ row.name }}</code><span>{{ row.sensitive ? '******' : row.value }}</span><button v-if="group.editable" :disabled="canEdit === false" type="button" :data-variable-remove="row.name" @click="remove(row)">删除</button></li></ul>
      </section>
    </template>
    <form @submit.prevent="save">
      <input v-model="form.name" data-variable-name placeholder="变量名" required />
      <select v-model="form.valueType"><option v-for="item in ['string','integer','decimal','boolean','date','datetime','json','array']" :key="item">{{ item }}</option></select>
      <input v-model="form.value" data-variable-value placeholder="变量值" required />
      <label><input v-model="form.sensitive" type="checkbox" />敏感</label>
      <button data-variable-save type="submit" :disabled="canEdit === false">保存（工作流域）</button>
    </form>
  </section>
</template>

<style scoped>
.workflow-variable-panel{position:absolute;z-index:20;right:10px;top:54px;width:380px;max-height:calc(100% - 70px);overflow:auto;background:#fff;border:1px solid #dbe3ef;border-radius:8px;box-shadow:0 10px 28px #0f172a20;padding:12px}
header,li,form{display:flex;align-items:center;gap:8px}header{justify-content:space-between}ul{padding:0;list-style:none;margin:4px 0 0}li{padding:6px 0;border-bottom:1px solid #e2e8f0}li span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chain{display:flex;align-items:center;flex-wrap:wrap;gap:4px;margin:8px 0 4px;font-size:12px}
.chain-scope{padding:2px 7px;border:1px solid #cbd5e1;border-radius:999px;background:#f8fafc;color:#334155}
.chain-scope[data-chain-scope="workflow"]{border-color:#2563eb;background:#eff6ff;color:#1d4ed8}
.chain-arrow{color:#94a3b8}
.hint{margin:6px 0;color:#64748b;font-size:12px}
.preview{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:8px 0 10px;padding:8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px}
.preview input{flex:1;min-width:160px}
.preview p{width:100%;margin:0;font-size:12px;color:#334155}
.scope-group h4{margin:8px 0 0;font-size:12px;color:#475569}
.scope-group h4 small{margin-left:6px;font-weight:400;color:#94a3b8}
.error{color:#b91c1c}
input,select,button{font:inherit;padding:5px 7px}
</style>

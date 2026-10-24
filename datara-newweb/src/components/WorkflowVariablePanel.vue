<script setup lang="ts">
import { ref, watch } from 'vue'
import { createVariableContract, type VariableDefinition, type VariableValueType } from '../services/rebuild/variableApi'

const props = defineProps<{ modelValue: boolean; projectId: number; workflowId: number; canEdit?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const api = createVariableContract()
const rows = ref<VariableDefinition[]>([])
const loading = ref(false)
const error = ref('')
const form = ref({ name: '', value: '', valueType: 'string' as VariableValueType, sensitive: false })

async function load() {
  if (!props.modelValue) return
  loading.value = true
  error.value = ''
  try { rows.value = await api.listVariables(props.projectId, ['workflow'], { workflowId: props.workflowId }) }
  catch { error.value = '工作流变量加载失败' }
  finally { loading.value = false }
}

async function save() {
  if (!form.value.name.trim() || !form.value.value) return
  await api.saveVariable(props.projectId, { scope: 'workflow', workflowId: props.workflowId, ...form.value })
  form.value = { name: '', value: '', valueType: 'string', sensitive: false }
  await load()
}

async function remove(row: VariableDefinition) {
  await api.deleteVariable(props.projectId, 'workflow', row.name, { workflowId: props.workflowId })
  await load()
}

watch(() => [props.modelValue, props.projectId, props.workflowId], load, { immediate: true })
</script>

<template>
  <section v-if="modelValue" class="workflow-variable-panel" data-workflow-variable-panel>
    <header><strong>工作流变量</strong><button @click="emit('update:modelValue', false)">关闭</button></header>
    <p v-if="loading">加载中…</p><p v-else-if="error" class="error">{{ error }}</p>
    <ul v-else><li v-for="row in rows" :key="row.name"><code>{{ row.name }}</code><span>{{ row.sensitive ? '******' : row.value }}</span><button :disabled="canEdit === false" @click="remove(row)">删除</button></li></ul>
    <form @submit.prevent="save">
      <input v-model="form.name" data-variable-name placeholder="变量名" required />
      <select v-model="form.valueType"><option v-for="item in ['string','integer','decimal','boolean','date','datetime','json','array']" :key="item">{{ item }}</option></select>
      <input v-model="form.value" data-variable-value placeholder="变量值" required />
      <label><input v-model="form.sensitive" type="checkbox" />敏感</label>
      <button data-variable-save type="submit" :disabled="canEdit === false">保存</button>
    </form>
  </section>
</template>

<style scoped>
.workflow-variable-panel{position:absolute;z-index:20;right:10px;top:54px;width:360px;background:#fff;border:1px solid #dbe3ef;border-radius:8px;box-shadow:0 10px 28px #0f172a20;padding:12px}header,li,form{display:flex;align-items:center;gap:8px}header{justify-content:space-between}ul{padding:0;list-style:none}li{padding:7px 0;border-bottom:1px solid #e2e8f0}li span{flex:1}.error{color:#b91c1c}input,select,button{font:inherit;padding:5px 7px}
</style>

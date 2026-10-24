<script setup lang="ts">
import { ref } from 'vue'
import { createVariableContract, type VariableCompletionItem, type VariableContext, type VariableDiagnostic } from '../services/rebuild/variableApi'

const props = defineProps<{ modelValue: string; context: VariableContext; label?: string; multiline?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const api = createVariableContract()
const suggestions = ref<VariableCompletionItem[]>([])
const diagnostics = ref<VariableDiagnostic[]>([])
const currentValue = ref<string | null>(null)
const loading = ref(false)
const error = ref('')

async function onInput(event: Event) {
  const value = (event.target as HTMLInputElement).value
  emit('update:modelValue', value)
  error.value = ''
  try { suggestions.value = await api.completeVariables(value.slice(value.lastIndexOf('${')), props.context) }
  catch { suggestions.value = []; error.value = '补全加载失败' }
}

function choose(item: VariableCompletionItem) {
  const value = `\${${item.scope}.${item.name}}`
  emit('update:modelValue', value)
  suggestions.value = []
}

async function check() {
  loading.value = true
  error.value = ''
  try {
    const [checked, preview] = await Promise.all([
      api.checkReference(props.modelValue, props.context),
      api.previewResolution(props.modelValue, props.context),
    ])
    diagnostics.value = checked.diagnostics
    currentValue.value = preview.resolvedValue
  } catch { error.value = '变量校验失败' }
  finally { loading.value = false }
}
</script>

<template>
  <div class="variable-reference-input" data-variable-reference-input>
    <label v-if="label">{{ label }}</label>
    <div class="input-row">
      <textarea v-if="multiline" :value="modelValue" @input="onInput" />
      <input v-else :value="modelValue" @input="onInput" />
      <button data-variable-check type="button" :disabled="loading" @click="check">校验</button>
    </div>
    <div v-if="suggestions.length" class="suggestions" role="listbox">
      <button v-for="item in suggestions" :key="`${item.scope}.${item.name}`" data-variable-suggestion type="button" @click="choose(item)">
        {{ '${' + item.scope + '.' + item.name + '}' }} <small>{{ item.valueType }}</small>
      </button>
    </div>
    <ul v-if="diagnostics.length" class="diagnostics"><li v-for="item in diagnostics" :key="`${item.code}:${item.message}`"><strong>{{ item.code }}</strong> {{ item.message }}</li></ul>
    <p v-if="currentValue !== null" data-variable-current-value>当前值：{{ currentValue }}</p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<style scoped>
.variable-reference-input{display:grid;gap:6px}.input-row{display:flex;gap:6px}.input-row input,.input-row textarea{flex:1}.suggestions{display:grid;border:1px solid #dbe3ef;background:#fff}.suggestions button{text-align:left;border:0;border-bottom:1px solid #eef2f7;background:#fff;padding:6px}.diagnostics{margin:0;padding-left:20px;color:#b45309}.error{color:#b91c1c;margin:0}
</style>

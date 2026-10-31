<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { createVariableContract, type VariableCompletionItem, type VariableContext, type VariableDiagnostic } from '../services/rebuild/variableApi'

const props = defineProps<{ modelValue: string; context: VariableContext; label?: string; multiline?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const api = createVariableContract()
const suggestions = ref<VariableCompletionItem[]>([])
const diagnostics = ref<VariableDiagnostic[]>([])
const currentValue = ref<string | null>(null)
const loading = ref(false)
const error = ref('')
const editor = ref<HTMLInputElement | HTMLTextAreaElement | null>(null)
const completion = ref<{ source: string; start: number; end: number } | null>(null)

async function onInput(event: Event) {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement
  const value = target.value
  const cursor = target.selectionStart ?? value.length
  emit('update:modelValue', value)
  error.value = ''
  const start = value.lastIndexOf('${', cursor)
  const query = start >= 0 ? value.slice(start, cursor) : ''
  if (start < 0 || !/^\$\{[A-Za-z0-9_.-]*$/.test(query)) {
    completion.value = null
    suggestions.value = []
    return
  }
  completion.value = { source: value, start, end: cursor }
  try { suggestions.value = await api.completeVariables(query, props.context) }
  catch { suggestions.value = []; error.value = '补全加载失败' }
}

function choose(item: VariableCompletionItem) {
  const active = completion.value
  if (active === null) return
  const token = `\${${item.scope}.${item.name}}`
  const value = `${active.source.slice(0, active.start)}${token}${active.source.slice(active.end)}`
  emit('update:modelValue', value)
  suggestions.value = []
  completion.value = null
  nextTick(() => {
    const caret = active.start + token.length
    editor.value?.focus()
    editor.value?.setSelectionRange(caret, caret)
  })
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
      <textarea v-if="multiline" ref="editor" :value="modelValue" @input="onInput" />
      <input v-else ref="editor" :value="modelValue" @input="onInput" />
      <button data-variable-check type="button" :disabled="loading" @click="check">校验</button>
    </div>
    <div v-if="suggestions.length" class="suggestions" role="listbox">
      <button v-for="item in suggestions" :key="`${item.scope}.${item.name}`" data-variable-suggestion type="button" @click="choose(item)">
        <div class="var-row">
          <code class="var-token">{{ '${' + item.scope + '.' + item.name + '}' }}</code>
          <small class="var-type">{{ item.valueType }}</small>
          <small v-if="item.unavailableReason" class="var-unavailable" data-unavailable>{{ item.unavailableReason }}</small>
        </div>
        <div v-if="item.description || item.currentValue !== undefined" class="var-hint">
          <span v-if="item.description" class="var-desc">{{ item.description }}</span>
          <span v-if="item.currentValue !== undefined && item.currentValue !== null" class="var-current">现值：<code>{{ String(item.currentValue) }}</code></span>
        </div>
      </button>
    </div>
    <ul v-if="diagnostics.length" class="diagnostics"><li v-for="item in diagnostics" :key="`${item.code}:${item.message}`"><strong>{{ item.code }}</strong> {{ item.message }}</li></ul>
    <p v-if="currentValue !== null" data-variable-current-value>当前值：{{ currentValue }}</p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<style scoped>
.variable-reference-input{display:grid;gap:6px}.input-row{display:flex;gap:6px}.input-row input,.input-row textarea{flex:1}
.suggestions{display:grid;border:1px solid var(--border);background:var(--card);border-radius:4px;max-height:320px;overflow:auto}
.suggestions button{text-align:left;border:0;border-bottom:1px solid var(--border);background:transparent;padding:8px 10px;cursor:pointer}
.suggestions button:last-child{border-bottom:0}
.suggestions button:hover{background:var(--primary-light)}
.var-row{display:flex;gap:6px;align-items:baseline}.var-token{font-family:ui-monospace,monospace;color:var(--text)}.var-type{color:var(--text-2)}.var-unavailable{color:var(--danger)}
.var-hint{display:flex;gap:12px;margin-top:4px;font-size:12px;color:var(--text-2)}.var-desc{flex:1}.var-current code{background:var(--bg);padding:1px 4px;border-radius:3px;color:var(--text);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:bottom}
.diagnostics{margin:0;padding-left:20px;color:var(--warn)}.error{color:var(--danger);margin:0}
</style>

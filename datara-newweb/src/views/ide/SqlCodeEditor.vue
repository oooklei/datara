<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { basicSetup } from 'codemirror'
import { sql } from '@codemirror/lang-sql'
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { oneDark } from '@codemirror/theme-one-dark'

const props = defineProps<{ modelValue: string; placeholder?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const host = ref<HTMLElement | null>(null)
let view: EditorView | undefined

onMounted(() => {
  if (!host.value) return
  const extensions = [
    basicSetup,
    sql(),
    EditorView.lineWrapping,
    EditorView.updateListener.of((update) => {
      if (update.docChanged) emit('update:modelValue', update.state.doc.toString())
    }),
    EditorView.theme({
      '&': { height: '100%', fontSize: '13px' },
      '.cm-scroller': { fontFamily: 'var(--font-mono, ui-monospace, monospace)', overflow: 'auto' },
    }),
  ]
  if (document.documentElement.dataset.theme === 'dark') extensions.push(oneDark)
  view = new EditorView({
    parent: host.value,
    state: EditorState.create({ doc: props.modelValue, extensions }),
  })
})

watch(() => props.modelValue, (value) => {
  if (!view || value === view.state.doc.toString()) return
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } })
})

function updateFromBridge(event: Event) {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
}

function insertText(text: string) {
  if (!view) {
    emit('update:modelValue', `${props.modelValue}${text}`)
    return
  }
  const { from, to } = view.state.selection.main
  view.dispatch({ changes: { from, to, insert: text }, selection: { anchor: from + text.length }, scrollIntoView: true })
  view.focus()
}

defineExpose({ insertText, focus: () => view?.focus() })
onBeforeUnmount(() => view?.destroy())
</script>

<template>
  <div class="sql-code-editor" data-codemirror-editor>
    <div ref="host" class="sql-code-host" />
    <textarea
      class="sql-test-bridge"
      data-sql-editor
      :value="modelValue"
      :aria-label="placeholder ?? 'SQL 编辑器'"
      @input="updateFromBridge"
    />
  </div>
</template>

<style scoped>
.sql-code-editor{position:relative;height:100%;min-height:220px;border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden;background:var(--card)}
.sql-code-host{height:100%}
.sql-test-bridge{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}
</style>

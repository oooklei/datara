<!--
  FE-07a SQL 编辑器（从 R5-A 验证页复用，CodeMirror 6 轻量配置）。
  lang-sql 高亮 + 行号 + oneDark 主题；诊断面板可点击跳转。
-->
<template>
  <div class="ide-editor-wrap" data-testid="ide-sql-editor">
    <div ref="hostRef" class="ide-editor"></div>
    <div v-if="diagnostics.length" class="ide-diagnostics" data-testid="ide-diagnostics">
      <div v-for="item in diagnostics" :key="`${item.stmtIndex}:${item.line}:${item.col}:${item.code}`" class="ide-diagnostic" :class="`is-${item.severity}`" @click="goto(item.line, item.col)">
        <el-tag size="small" :type="item.severity === 'error' ? 'danger' : item.severity === 'warning' ? 'warning' : 'info'">{{ item.severity }}</el-tag>
        <strong>{{ item.code }}</strong><span>语句 {{ item.stmtIndex }} · {{ item.line }}:{{ item.col }}</span><span>{{ item.message }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorView, basicSetup } from 'codemirror'
import { EditorState } from '@codemirror/state'
import { sql } from '@codemirror/lang-sql'
import { oneDark } from '@codemirror/theme-one-dark'
import type { SqlDiagnostic } from '../../../services/rebuild/sqlIdeApi'

const props = withDefaults(defineProps<{ modelValue: string; readonly?: boolean; diagnostics?: SqlDiagnostic[] }>(), { diagnostics: () => [] })
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const hostRef = ref<HTMLDivElement | null>(null)
let view: EditorView | null = null
const diagnostics = computed(() => props.diagnostics)

function goto(lineNumber: number, column: number) {
  if (!view) return
  const line = view.state.doc.line(Math.max(1, Math.min(lineNumber, view.state.doc.lines)))
  const position = Math.min(line.to, line.from + Math.max(0, column - 1))
  view.dispatch({ selection: { anchor: position }, effects: EditorView.scrollIntoView(position, { y: 'center' }) })
  view.focus()
}

onMounted(() => {
  const state = EditorState.create({
    doc: props.modelValue,
    selection: { anchor: props.modelValue.length },
    extensions: [
      basicSetup,
      sql(),
      oneDark,
      EditorView.lineWrapping,
      EditorView.editable.of(!props.readonly),
      EditorView.updateListener.of((u) => {
        if (u.docChanged) emit('update:modelValue', u.state.doc.toString())
      }),
    ],
  })
  view = new EditorView({ parent: hostRef.value!, state })
})

watch(
  () => props.modelValue,
  (v) => {
    if (view && v !== view.state.doc.toString()) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: v } })
    }
  },
)

onBeforeUnmount(() => view?.destroy())
</script>

<style scoped>
.ide-editor-wrap { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.ide-editor {
  height: 100%;
  min-height: 0;
  flex: 1;
  overflow: auto;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  background: #282c34;
}
.ide-editor :deep(.cm-editor) {
  height: 100%;
}
.ide-diagnostics { flex: none; max-height: 132px; overflow: auto; border-top: 1px solid var(--el-border-color); background: var(--el-bg-color); }
.ide-diagnostic { display: flex; align-items: center; gap: 8px; padding: 4px 8px; cursor: pointer; font-size: 12px; }
.ide-diagnostic:hover { background: var(--el-fill-color-light); }
</style>

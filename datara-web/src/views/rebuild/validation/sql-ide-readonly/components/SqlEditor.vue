<!--
  R5-A 验证页专用 SQL 编辑器（原型态）。
  与正式 IDE（src/views/ide/components/SqlEditor.vue）完全独立：验证页用 CodeMirror 6 轻量配置
  （lang-sql 高亮 + 行号 + oneDark），Monaco 级体验（补全/多语句高亮）按影响分析决策点 2 留给融合阶段。
  不引入 monaco-editor，避免验证页大包。
-->
<template>
  <div class="r5a-editor-wrap" data-testid="r5a-sql-editor">
    <div ref="hostRef" class="r5a-editor"></div>
    <div v-if="diagnostics.length" class="r5a-diagnostics" data-testid="r5a-diagnostics">
      <div v-for="item in diagnostics" :key="`${item.stmtIndex}:${item.line}:${item.col}:${item.code}`" class="r5a-diagnostic" :class="`is-${item.severity}`" @click="goto(item.line, item.col)">
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
import type { SqlDiagnostic } from '../../../../../services/rebuild/sqlIdeApi'

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
.r5a-editor-wrap { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.r5a-editor {
  height: 100%;
  min-height: 0;
  flex: 1;
  overflow: auto;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  background: #282c34;
}
.r5a-editor :deep(.cm-editor) {
  height: 100%;
}
.r5a-diagnostics { flex: none; max-height: 132px; overflow: auto; border-top: 1px solid var(--el-border-color); background: var(--el-bg-color); }
.r5a-diagnostic { display: flex; align-items: center; gap: 8px; padding: 4px 8px; cursor: pointer; font-size: 12px; }
.r5a-diagnostic:hover { background: var(--el-fill-color-light); }
</style>

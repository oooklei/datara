<!--
  R5-A 验证页专用 SQL 编辑器（原型态）。
  与正式 IDE（src/views/ide/components/SqlEditor.vue）完全独立：验证页用 CodeMirror 6 轻量配置
  （lang-sql 高亮 + 行号 + oneDark），Monaco 级体验（补全/多语句高亮）按影响分析决策点 2 留给融合阶段。
  不引入 monaco-editor，避免验证页大包。
-->
<template>
  <div ref="hostRef" class="r5a-editor" data-testid="r5a-sql-editor"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorView, basicSetup } from 'codemirror'
import { EditorState } from '@codemirror/state'
import { sql } from '@codemirror/lang-sql'
import { oneDark } from '@codemirror/theme-one-dark'

const props = defineProps<{ modelValue: string; readonly?: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const hostRef = ref<HTMLDivElement | null>(null)
let view: EditorView | null = null

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
.r5a-editor {
  height: 100%;
  overflow: auto;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  background: #282c34;
}
.r5a-editor :deep(.cm-editor) {
  height: 100%;
}
</style>

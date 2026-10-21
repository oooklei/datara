<template><section class="source-editor" data-track="source" aria-label="源码文本编辑轨">
  <header class="track-head">
    <h2>源码文本编辑轨</h2>
    <p>非 table 对象（ObjectSourceKind 13 变体）走源码文本编辑；TABLE/INDEX 不入本轨——表结构走独立元数据通道，索引为表子对象。</p>
  </header>
  <DdlSnapshotMeta v-if="snapshot" :snapshot="snapshot" />
  <p v-else class="empty" role="status">尚未载入对象定义快照（载入后方可在快照绑定链上编辑）。</p>
  <label class="field wide"><span>当前定义（只读）</span>
    <textarea data-current-definition rows="6" readonly :value="snapshot?.definition ?? ''" :disabled="!snapshot"></textarea>
  </label>
  <label class="field wide"><span>下一版 DDL（nextDdlText）</span>
    <textarea data-source-input rows="10" :value="modelValue" :disabled="!snapshot" placeholder="编辑下一版 DDL 文本" @input="onInput"></textarea>
  </label>
</section></template>

<script setup lang="ts">
/**
 * 16.1 波3 源码文本编辑轨：非 table 对象（ObjectSourceKind 13 变体）DDL 源码编辑。
 * 编辑器现态=轻量 textarea（组件契约测试稳定性优先）；codemirror 6 换芯
 * 登记候接（不阻塞八步管控语义）。
 */
import type { DdlDefinitionSnapshot } from '../../../services/rebuild/sqlIdeDdlApi'
import DdlSnapshotMeta from './DdlSnapshotMeta.vue'

defineProps<{ snapshot: DdlDefinitionSnapshot | null; modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

function onInput(event: Event) {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
}
</script>

<style scoped>
.source-editor{border:1px solid #e2e8f0;border-radius:8px;padding:16px;background:#fff}
.track-head h2{margin:0 0 4px;font-size:16px}
.track-head p{margin:0 0 12px;color:#64748b;font-size:13px}
.empty{color:#94a3b8;font-size:13px;margin:0 0 12px}
.field{display:flex;flex-direction:column;gap:4px;margin-bottom:10px;font-size:13px}
.field.wide{width:100%}
.field span{color:#475569}
textarea{width:100%;box-sizing:border-box;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;line-height:1.5;padding:8px;border:1px solid #cbd5e1;border-radius:6px;color:#172033;background:#fff}
textarea[readonly]{background:#f8fafc;color:#475569}
textarea:disabled{background:#f1f5f9;color:#94a3b8}
</style>

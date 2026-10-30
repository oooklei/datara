<template><section class="structured-editor" data-track="structured" aria-label="结构化编辑轨">
  <header class="track-head">
    <h2>结构化编辑轨</h2>
    <p>table 目标仅允许结构化变更操作派生 DDL（不得以源码编辑器代替）：当前支持 add_column / drop_column。</p>
  </header>
  <DdlSnapshotMeta v-if="snapshot" :snapshot="snapshot" />
  <p v-else class="empty" role="status">尚未载入对象定义快照（载入后方可在快照绑定链上编辑）。</p>
  <fieldset class="ops" :disabled="!snapshot">
    <legend>结构化变更操作</legend>
    <label class="field"><span>操作</span>
      <select data-op-select v-model="op">
        <option value="add_column">add_column（新增列）</option>
        <option value="drop_column">drop_column（删除列）</option>
      </select>
    </label>
    <label class="field"><span>列名</span>
      <input data-column-name v-model="columnName" placeholder="例如 remark" />
    </label>
    <label v-if="op === 'add_column'" class="field"><span>列类型</span>
      <input data-column-type v-model="columnType" placeholder="例如 VARCHAR(64)" />
    </label>
  </fieldset>
  <label class="field wide"><span>派生 DDL（只读）</span>
    <textarea data-generated-ddl rows="3" readonly :value="generated"></textarea>
  </label>
</section></template>

<script setup lang="ts">
/**
 * 16.1 波3 结构化编辑轨：kind=table 专用（双轨互斥，禁自由源码输入——无
 * data-source-input 锚）。DDL 文本由结构化操作派生，经 v-model 上行至容器
 * nextDdlText，进入八步管控面（依赖检查→策略→确认→执行→记录）。
 */
import { computed, ref, watch } from 'vue'
import type { DdlDefinitionSnapshot } from '../../../services/rebuild/sqlIdeDdlApi'
import DdlSnapshotMeta from './DdlSnapshotMeta.vue'

const props = defineProps<{ snapshot: DdlDefinitionSnapshot | null; modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

type StructuredOp = 'add_column' | 'drop_column'
const op = ref<StructuredOp>('add_column')
const columnName = ref('')
const columnType = ref('')

const generated = computed(() => {
  if (props.snapshot === null) return ''
  const table = props.snapshot.objectRef.name
  const column = columnName.value.trim()
  if (op.value === 'add_column') {
    const type = columnType.value.trim()
    if (column === '' || type === '') return ''
    return `ALTER TABLE ${table} ADD COLUMN ${column} ${type}`
  }
  if (column === '') return ''
  return `ALTER TABLE ${table} DROP COLUMN ${column}`
})

watch(generated, (value) => { emit('update:modelValue', value) })

// 容器 resetChain（nextDdlText 置空）时同步清空表单，防 generated/modelValue 失步。
watch(() => props.modelValue, (value) => {
  if (value === '') { columnName.value = ''; columnType.value = '' }
})
</script>

<style scoped>
/* 设计令牌：由全局 styles/theme.css 的 :root 提供（§4.4.3 风格统一），本文件不再就地重复定义。 */
.structured-editor{border:1px solid var(--border);border-radius:var(--radius);padding:16px;background:var(--card)}
.track-head h2{margin:0 0 4px;font-size:16px}
.track-head p{margin:0 0 12px;color:var(--text-3);font-size:13px}
.empty{color:var(--text-3);font-size:13px;margin:0 0 12px}
.ops{border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px;margin:0 0 10px;display:flex;gap:12px;flex-wrap:wrap}
.ops legend{color:var(--text-2);font-size:13px;padding:0 4px}
.field{display:flex;flex-direction:column;gap:4px;font-size:13px}
.field.wide{width:100%}
.field span{color:var(--text-2)}
input,select{padding:6px 8px;border:1px solid var(--border-strong);border-radius:var(--radius-sm);font-size:13px;color:var(--text);background:var(--card)}
textarea{width:100%;box-sizing:border-box;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;line-height:1.5;padding:8px;border:1px solid var(--border-strong);border-radius:var(--radius-sm);color:var(--text);background:var(--bg)}
fieldset:disabled input,fieldset:disabled select{background:var(--bg);color:var(--text-3)}
</style>

<script setup lang="ts">
/**
 * F60 行编辑表渲染器：kv-table（键/值/说明）、params-table（键/值/来源五选一）
 * 与 I4 args-table（键/方向 IN|OUT/值，C15 存储过程参数）共用。
 * I7 追加 vars 模式（C21 变量表：名/值/类型[字面量|表达式|时间变量]/覆盖开关，设计 §3.1）。
 * 直接编辑传入 rows（引用自 node.data），变更后 emit('change') 由父层 markDirty 持久化。
 * params 来源对齐 02 文档 §1.2：全局变量|工作流变量|环境组|字面量|时间变量。
 */
export type KvRow = { k: string; v: string; note?: string }
export type ParamRow = { key: string; value: string; source: string }
export type ArgRow = { key: string; direction: string; value: string }
export type VarRow = { name: string; value: string; type: string; override: boolean }

const props = defineProps<{
  rows: { [k: string]: unknown }[]
  mode: 'kv' | 'params' | 'args' | 'vars'
  disabled?: boolean
}>()
const emit = defineEmits<{ (e: 'change'): void }>()

const SOURCES = [
  { value: 'literal', label: '字面量' },
  { value: 'global', label: '全局变量' },
  { value: 'workflow', label: '工作流变量' },
  { value: 'env', label: '环境组' },
  { value: 'time', label: '时间变量' },
]

/** I7 C21 变量类型（设计 §0① 三选一；time 值=F49 时间模板如 yyyyMMdd-1） */
const VAR_TYPES = [
  { value: 'literal', label: '字面量' },
  { value: 'expr', label: '表达式' },
  { value: 'time', label: '时间变量' },
]

function addRow() {
  if (props.mode === 'kv') props.rows.push({ k: '', v: '', note: '' })
  else if (props.mode === 'args') props.rows.push({ key: '', direction: 'IN', value: '' })
  else if (props.mode === 'vars') props.rows.push({ name: '', value: '', type: 'literal', override: false })
  else props.rows.push({ key: '', value: '', source: 'literal' })
  emit('change')
}

function delRow(i: number) {
  props.rows.splice(i, 1)
  emit('change')
}

function setCell(row: { [k: string]: unknown }, field: string, ev: Event) {
  const t = ev.target as HTMLInputElement | HTMLSelectElement
  row[field] = t.value
  emit('change')
}

/** I7 vars 模式：覆盖开关（checkbox） */
function setCheck(row: { [k: string]: unknown }, field: string, ev: Event) {
  row[field] = (ev.target as HTMLInputElement).checked
  emit('change')
}
</script>

<template>
  <div class="rowsf">
    <table class="rowsf-tbl">
      <thead>
        <tr>
          <template v-if="mode === 'kv'"><th>键</th><th>值</th><th>说明</th></template>
          <template v-else-if="mode === 'args'"><th>参数名</th><th>方向</th><th>值</th></template>
          <template v-else-if="mode === 'vars'"><th>变量名</th><th>值</th><th>类型</th><th>覆盖</th></template>
          <template v-else><th>参数名</th><th>值</th><th>来源</th></template>
          <th class="rowsf-op"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in rows" :key="i">
          <template v-if="mode === 'kv'">
            <td><input :value="String(r.k ?? '')" :disabled="disabled" @change="setCell(r, 'k', $event)" /></td>
            <td><input :value="String(r.v ?? '')" :disabled="disabled" @change="setCell(r, 'v', $event)" /></td>
            <td><input :value="String(r.note ?? '')" :disabled="disabled" @change="setCell(r, 'note', $event)" /></td>
          </template>
          <template v-else-if="mode === 'args'">
            <td><input :value="String(r.key ?? '')" :disabled="disabled" @change="setCell(r, 'key', $event)" /></td>
            <td>
              <select :value="String(r.direction ?? 'IN')" :disabled="disabled" @change="setCell(r, 'direction', $event)">
                <option value="IN">IN</option>
                <option value="OUT">OUT</option>
              </select>
            </td>
            <td><input :value="String(r.value ?? '')" :disabled="disabled || String(r.direction ?? 'IN') === 'OUT'" placeholder="OUT 参数无需传值" @change="setCell(r, 'value', $event)" /></td>
          </template>
          <template v-else-if="mode === 'vars'">
            <td><input :value="String(r.name ?? '')" :disabled="disabled" placeholder="如 wf.period" @change="setCell(r, 'name', $event)" /></td>
            <td><input :value="String(r.value ?? '')" :disabled="disabled" placeholder="字面量 / 表达式 / yyyyMMdd-1" @change="setCell(r, 'value', $event)" /></td>
            <td>
              <select :value="String(r.type ?? 'literal')" :disabled="disabled" @change="setCell(r, 'type', $event)">
                <option v-for="t in VAR_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
              </select>
            </td>
            <td class="rowsf-ck"><input type="checkbox" :checked="!!r.override" :disabled="disabled" title="开=覆盖定义级同名变量" @change="setCheck(r, 'override', $event)" /></td>
          </template>
          <template v-else>
            <td><input :value="String(r.key ?? '')" :disabled="disabled" @change="setCell(r, 'key', $event)" /></td>
            <td><input :value="String(r.value ?? '')" :disabled="disabled" @change="setCell(r, 'value', $event)" /></td>
            <td>
              <select :value="String(r.source ?? 'literal')" :disabled="disabled" @change="setCell(r, 'source', $event)">
                <option v-for="s in SOURCES" :key="s.value" :value="s.value">{{ s.label }}</option>
              </select>
            </td>
          </template>
          <td class="rowsf-op"><button :disabled="disabled" title="删除该行" @click="delRow(i)">×</button></td>
        </tr>
        <tr v-if="!rows.length"><td colspan="4" class="rowsf-empty">暂无{{ mode === 'kv' ? '键值' : mode === 'args' ? '过程参数' : mode === 'vars' ? '变量' : '参数' }}行</td></tr>
      </tbody>
    </table>
    <button v-if="!disabled" class="rowsf-add" @click="addRow">＋ 新增</button>
  </div>
</template>

<style scoped>
.rowsf-tbl{width:100%;border-collapse:collapse;font-size:11px}
.rowsf-tbl th{text-align:left;font-weight:600;color:var(--text-3);padding:2px 3px;border-bottom:1px solid var(--border)}
.rowsf-tbl td{padding:2px 3px;border-bottom:1px dashed var(--border)}
.rowsf-tbl input,.rowsf-tbl select{width:100%;min-width:0;border:1px solid var(--border);border-radius:var(--radius-sm);padding:3px 5px;font-size:11px;outline:none}
.rowsf-tbl input:focus,.rowsf-tbl select:focus{border-color:var(--primary)}
.rowsf-op{width:20px}
.rowsf-ck{text-align:center}
.rowsf-ck input{width:auto;cursor:pointer}
.rowsf-op button{width:18px;height:18px;border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);color:var(--text-3);font-size:11px;line-height:1;cursor:pointer}
.rowsf-op button:hover:not(:disabled){border-color:var(--danger);color:var(--danger)}
.rowsf-op button:disabled{opacity:.4;cursor:not-allowed}
.rowsf-empty{text-align:center;color:var(--text-3);padding:6px 0;font-size:11px}
.rowsf-add{margin-top:4px;width:100%;border:1px dashed var(--border-strong);background:var(--bg);border-radius:var(--radius-sm);padding:4px 0;font-size:11px;color:var(--text-2);cursor:pointer}
.rowsf-add:hover{border-color:var(--primary);color:var(--primary)}
</style>

<script setup lang="ts">
/**
 * fields 声明式组件·表单定义预览（画布区）。
 * 逐字段渲染「标签 + 控件占位」，控件按 uiType 9 基元映射（disabled 预览语义，
 * 值显示字段 default；编辑动作在右侧 FieldsInspector）。
 * 点击行选中（emit select idx）；空声明落引导空态。原生控件 + 本组件样式，
 * 避免 el-* 桩噪音并保证快照稳定。
 */
import type { FieldRow } from './fieldsModel'

defineProps<{ rows: FieldRow[]; selectedIdx: number }>()
const emit = defineEmits<{ (e: 'select', idx: number): void }>()

const UI_LABEL: Record<string, string> = {
  text: '文本', number: '数值', bool: '开关', select: '下拉', expr: '表达式',
  hint: '提示', rows: '行编辑表', mapEditor: '映射编辑', resource: '资源选择',
}
function uiLabel(t: string): string {
  return UI_LABEL[t] ?? t
}
/** default 展示文本（非字符串 JSON 化；对象/数组短截断） */
function defaultText(row: FieldRow): string {
  const v = row.default
  if (v === undefined || v === null) return ''
  const s = typeof v === 'string' ? v : JSON.stringify(v)
  return s.length > 60 ? `${s.slice(0, 60)}…` : s
}
function isMultiLine(t: string): boolean {
  return t === 'expr' || t === 'rows' || t === 'mapEditor'
}
</script>

<template>
  <div class="fc-wrap">
    <div class="fc-card" data-testid="fc-card">
      <div class="fc-head">
        <span class="fc-title">参数表单预览</span>
        <span class="fc-sub">{{ rows.length }} 个字段（拖入组件时弹窗填写）</span>
      </div>
      <div v-if="rows.length === 0" class="fc-empty" data-testid="fc-empty">
        暂无表单字段——在右侧属性面板「添加字段」定义该组件的参数表单
      </div>
      <div
        v-for="(row, i) in rows" :key="i" class="fc-row" :class="{ 'is-sel': i === selectedIdx }"
        :data-testid="`fc-row-${i}`" @click="emit('select', i)"
      >
        <label class="fc-label" :title="row.key ? String(row.key) : ''">
          <span v-if="row.required" class="fc-req">*</span>{{ row.label || row.key || '(未命名字段)' }}
          <span class="fc-uitype">{{ uiLabel(String(row.uiType)) }}</span>
        </label>
        <div v-if="row.uiType === 'hint'" class="fc-hint">{{ row.label || defaultText(row) || '提示信息' }}</div>
        <template v-else>
          <input
            v-if="row.uiType === 'number'" class="fc-ctl" type="number"
            :value="defaultText(row)" disabled :placeholder="uiLabel(row.uiType)"
          >
          <div v-else-if="row.uiType === 'bool'" class="fc-bool">
            <span class="fc-switch" :class="{ on: row.default === true }" />
            <span class="fc-bool-text">{{ row.default === true ? '开' : '关' }}</span>
          </div>
          <select v-else-if="row.uiType === 'select'" class="fc-ctl" disabled>
            <option value="">{{ defaultText(row) || uiLabel(row.uiType) }}</option>
          </select>
          <textarea
            v-else-if="isMultiLine(row.uiType)" class="fc-ctl fc-area" disabled
            :value="defaultText(row)" :placeholder="uiLabel(row.uiType)" rows="2"
          />
          <div v-else-if="row.uiType === 'resource'" class="fc-ctl fc-res">
            <span class="fc-res-text">{{ defaultText(row) || '资源选择器' }}</span>
            <span class="fc-res-badge">{{ uiLabel(row.uiType) }}</span>
          </div>
          <input v-else class="fc-ctl" :value="defaultText(row)" disabled placeholder="文本">
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fc-wrap {
  padding: 24px;
  display: flex;
  justify-content: center;
}
.fc-card {
  width: 420px;
  max-width: 100%;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow, 0 2px 8px rgba(0, 0, 0, 0.06));
  padding: 14px 16px 16px;
  align-self: flex-start;
}
.fc-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 10px;
}
.fc-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.fc-sub {
  font-size: 11px;
  color: var(--text-3);
}
.fc-empty {
  padding: 26px 8px;
  text-align: center;
  font-size: 12px;
  color: var(--text-3);
}
.fc-row {
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm, 6px);
  cursor: pointer;
  transition: border-color var(--dur-fast, 0.15s) var(--ease, ease), background var(--dur-fast, 0.15s) var(--ease, ease);
}
.fc-row + .fc-row {
  margin-top: 2px;
}
.fc-row:hover {
  background: var(--primary-light, rgba(22, 119, 255, 0.06));
}
.fc-row.is-sel {
  border-color: var(--primary);
  background: var(--primary-light, rgba(22, 119, 255, 0.06));
}
.fc-label {
  display: block;
  font-size: 12px;
  color: var(--text-2);
  margin-bottom: 4px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.fc-req {
  color: var(--danger, #f56c6c);
  margin-right: 2px;
}
.fc-uitype {
  float: right;
  font-size: 10px;
  color: var(--text-3);
  background: var(--bg, rgba(0, 0, 0, 0.04));
  border-radius: 4px;
  padding: 0 4px;
}
.fc-ctl {
  width: 100%;
  box-sizing: border-box;
  height: 28px;
  padding: 0 8px;
  font-size: 12px;
  color: var(--text-2);
  background: var(--bg, rgba(0, 0, 0, 0.03));
  border: 1px solid var(--border);
  border-radius: 6px;
  opacity: 1;
  cursor: default;
}
.fc-ctl:disabled {
  background: var(--bg, rgba(0, 0, 0, 0.03));
}
.fc-area {
  height: auto;
  padding: 6px 8px;
  resize: none;
  font-family: inherit;
}
.fc-bool {
  display: flex;
  align-items: center;
  gap: 8px;
}
.fc-switch {
  width: 30px;
  height: 16px;
  border-radius: 8px;
  background: var(--border);
  position: relative;
  flex: none;
}
.fc-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #fff;
  transition: left var(--dur-fast, 0.15s) var(--ease, ease);
}
.fc-switch.on {
  background: var(--primary, #1677ff);
}
.fc-switch.on::after {
  left: 16px;
}
.fc-bool-text {
  font-size: 11px;
  color: var(--text-3);
}
.fc-hint {
  font-size: 12px;
  color: var(--info, #409eff);
  background: var(--info-bg, rgba(64, 158, 255, 0.08));
  border-radius: 6px;
  padding: 6px 10px;
}
.fc-res {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.fc-res-text {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.fc-res-badge {
  flex: none;
  font-size: 10px;
  color: var(--primary);
  border: 1px solid var(--primary);
  border-radius: 4px;
  padding: 0 4px;
  opacity: 0.7;
}
</style>

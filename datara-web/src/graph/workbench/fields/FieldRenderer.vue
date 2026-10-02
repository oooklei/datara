<script setup lang="ts">
import type { FieldSchema } from '../../profiles/types'
import type { FieldCtx } from './fieldCtx'

defineProps<{
  field: FieldSchema
  data: Record<string, unknown>
  mode: 'edit' | 'view'
  nodeId: string
  ctx: FieldCtx
}>()

const emit = defineEmits<{
  set: [FieldSchema, Event]
  dirty: []
  openVarDialog: []
  focusTarget: []
}>()

function valueOf(field: FieldSchema, data: Record<string, unknown>): string | number | boolean {
  const value = data[field.key]
  if (field.type === 'bool') return value === true
  if (field.type === 'number') return typeof value === 'number' ? value : Number(value ?? 0)
  return value == null ? '' : String(value)
}

function textValue(field: FieldSchema, data: Record<string, unknown>): string {
  return String(valueOf(field, data))
}

function hintText(field: FieldSchema, data: Record<string, unknown>): string | undefined {
  return typeof field.text === 'function' ? field.text(data) : field.text ?? field.placeholder
}
</script>

<template>
  <div class="field-renderer">
    <span v-if="field.type === 'hint'" class="hint">{{ hintText(field, data) }}</span>
    <input
      v-else-if="field.type === 'number'"
      type="number"
      :value="textValue(field, data)"
      :readonly="mode === 'view'"
      @input="emit('set', field, $event); emit('dirty')"
    />
    <label v-else-if="field.type === 'bool'" class="check">
      <input
        type="checkbox"
        :checked="valueOf(field, data) === true"
        :disabled="mode === 'view'"
        @change="emit('set', field, $event); emit('dirty')"
      />
      <span>{{ field.placeholder || field.label }}</span>
    </label>
    <select
      v-else-if="field.type === 'select'"
      :value="textValue(field, data)"
      :disabled="mode === 'view'"
      @change="emit('set', field, $event); emit('dirty')"
    >
      <option value="">请选择</option>
      <option v-for="o in field.options ?? []" :key="o.value" :value="o.value">{{ o.label }}</option>
    </select>
    <textarea
      v-else-if="field.type === 'textarea' || field.type === 'script' || field.type === 'expr'"
      :value="textValue(field, data)"
      :readonly="mode === 'view'"
      :placeholder="field.placeholder"
      @input="emit('set', field, $event); emit('dirty')"
    />
    <input
      v-else
      type="text"
      :value="valueOf(field, data)"
      :readonly="mode === 'view'"
      :placeholder="field.placeholder"
      @input="emit('set', field, $event); emit('dirty')"
    />
  </div>
</template>

<style scoped>
.field-renderer,
input,
select,
textarea {
  width: 100%;
}
input,
select,
textarea {
  border: 1px solid #dbe3ef;
  border-radius: 4px;
  padding: 6px 8px;
  font-size: 12px;
  box-sizing: border-box;
}
textarea {
  min-height: 72px;
  resize: vertical;
}
.check {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
}
.check input {
  width: auto;
}
.hint {
  display: block;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}
</style>

<script setup lang="ts">
/**
 * Task 6（方案§2.1/§2.6）契约页签：8 要素之 fields + outputs。
 * - fields 行编辑：key/label/uiType（SPEC_UI_TYPES 9 基元）/required/layer 直改，事件语义与
 *   FieldsInspector 一致（patchRow/addRow/removeRow/moveRow），宿主 FieldsState.rows 单一状态源；
 *   字段默认值/说明/select 候选等详编在右侧 FieldsInspector（划界：本组件管行级快改）。
 * - 输出定义编辑器：outputs 行编辑（name/type 下拉/desc），type 选项取 portTypes.TYPE_COMPAT
 *   键集合（DataType 九值交集矩阵的源类型域）。
 * 控件复用划界：本组件编辑「声明结构元数据」，与拖入弹窗/Inspector 的 9 基元控件渲染层
 * （SixBlocks+FieldRenderer，渲染运行时控件实例）分属不同层，uiType 枚举统一引 SPEC_UI_TYPES 不双写。
 * 打字即校验：violations 由宿主 validateSpecPureData 下发（fields[i].x / outputs[i].x 前缀红标）。
 */
import { computed } from 'vue'
import { SPEC_UI_TYPES, type SpecViolation } from '../../services/componentSpec'
import { TYPE_COMPAT } from '../../graph/model/portTypes'
import type { FieldRow, FieldsSource, DeclOutput } from '../../views/meta/pageDesigner/fields/fieldsModel'

const props = defineProps<{
  rows: FieldRow[]
  source: FieldsSource
  outputs?: DeclOutput[]
  violations: SpecViolation[]
}>()
const emit = defineEmits<{
  (e: 'patchRow', idx: number, patch: Record<string, unknown>): void
  (e: 'addRow'): void
  (e: 'removeRow', idx: number): void
  (e: 'moveRow', idx: number, dir: -1 | 1): void
  (e: 'updateOutputs', list: DeclOutput[] | undefined): void
}>()

/** 输出 type 下拉：TYPE_COMPAT 键集合（8 源类型；any 由「未声明」语义承载，不入候选） */
const OUTPUT_TYPES = Object.keys(TYPE_COMPAT)
const LAYERS = [
  { value: 'required', label: '必填' },
  { value: 'optional', label: '可选' },
  { value: 'hidden', label: '隐藏' },
]

const outputs = computed<DeclOutput[]>(() => props.outputs ?? [])
/** 行内红标：path 前缀匹配（fields[0].label 命中 fields[0]） */
function bad(prefix: string): boolean {
  return props.violations.some((v) => v.path === prefix || v.path.startsWith(`${prefix}.`) || v.path.startsWith(`${prefix}[`))
}
function rowBad(i: number): boolean {
  return bad(`fields[${i}]`)
}
function layerOf(r: FieldRow): string {
  return typeof r.layer === 'string' ? r.layer : 'required'
}
function patchLayer(i: number, v: string): void {
  emit('patchRow', i, { layer: v })
}
function setOutput(i: number, k: 'name' | 'type' | 'desc', v: string): void {
  emit('updateOutputs', outputs.value.map((o, xi) => (xi === i ? { ...o, [k]: v } : o)))
}
function addOutput(): void {
  emit('updateOutputs', [...outputs.value, { name: '', type: 'table' }])
}
function removeOutput(i: number): void {
  const next = outputs.value.filter((_, xi) => xi !== i)
  emit('updateOutputs', next.length ? next : undefined) // 删光 = 未声明
}
</script>

<template>
  <div class="sf" data-testid="sf-contract">
    <div class="sf-sec">
      参数表单字段
      <span class="sf-count">{{ rows.length }} 项</span>
      <el-button size="small" type="primary" plain data-testid="sf-ct-add" @click="emit('addRow')">添加字段</el-button>
    </div>
    <div v-if="rows.length === 0" class="sf-empty">暂无字段——添加后定义该组件拖入时的参数表单</div>
    <div
      v-for="(r, i) in rows" :key="i" class="sf-grid-row" :data-testid="`sf-ct-row-${i}`"
      :class="{ 'sf-bad-border': rowBad(i) }"
    >
      <el-input
        :model-value="r.key" placeholder="key" :class="{ 'sf-bad': bad(`fields[${i}].key`) }"
        @update:model-value="emit('patchRow', i, { key: $event })"
      />
      <el-input
        :model-value="r.label" placeholder="名称" :class="{ 'sf-bad': bad(`fields[${i}].label`) }"
        @update:model-value="emit('patchRow', i, { label: $event })"
      />
      <el-select
        :model-value="r.uiType" placeholder="控件" :class="{ 'sf-bad': bad(`fields[${i}].uiType`) }"
        @update:model-value="emit('patchRow', i, { uiType: $event })"
      >
        <el-option v-for="t in SPEC_UI_TYPES" :key="t.value" :label="`${t.label}（${t.value}）`" :value="t.value" />
      </el-select>
      <el-select :model-value="layerOf(r)" @update:model-value="patchLayer(i, String($event))">
        <el-option v-for="l in LAYERS" :key="l.value" :label="l.label" :value="l.value" />
      </el-select>
      <el-switch
        :model-value="r.required === true" title="required"
        @update:model-value="emit('patchRow', i, { required: $event === true })"
      />
      <span class="sf-acts">
        <button type="button" class="sf-mini" title="上移" :disabled="i === 0" @click="emit('moveRow', i, -1)">↑</button>
        <button type="button" class="sf-mini" title="下移" :disabled="i === rows.length - 1" @click="emit('moveRow', i, 1)">↓</button>
        <button type="button" class="sf-mini sf-mini-danger" title="删除" @click="emit('removeRow', i)">删</button>
      </span>
    </div>

    <div class="sf-sec">
      输出定义
      <span class="sf-count">{{ outputs.length }} 项</span>
      <el-button size="small" type="primary" plain data-testid="sf-ct-out-add" @click="addOutput">添加输出</el-button>
    </div>
    <div class="sf-note">供连线类型推断/预览消费（区别于 ports 物理端口）；数据组件未声明 outputs 记缺项</div>
    <div v-if="outputs.length === 0" class="sf-empty">未声明输出</div>
    <div v-for="(o, i) in outputs" :key="i" class="sf-grid-row" :data-testid="`sf-ct-out-${i}`">
      <el-input
        :model-value="o.name" placeholder="输出名" :class="{ 'sf-bad': bad(`outputs[${i}].name`) }"
        @update:model-value="setOutput(i, 'name', $event)"
      />
      <el-select
        :model-value="o.type" placeholder="类型" :class="{ 'sf-bad': bad(`outputs[${i}].type`) }"
        @update:model-value="setOutput(i, 'type', String($event))"
      >
        <el-option v-for="t in OUTPUT_TYPES" :key="t" :label="t" :value="t" />
      </el-select>
      <el-input
        :model-value="o.desc ?? ''" placeholder="说明（可空）" class="sf-out-desc"
        :class="{ 'sf-bad': bad(`outputs[${i}].desc`) }" @update:model-value="setOutput(i, 'desc', $event)"
      />
      <span class="sf-acts">
        <button type="button" class="sf-mini sf-mini-danger" title="删除输出" @click="removeOutput(i)">删</button>
      </span>
    </div>
    <div class="sf-note">来源：{{ source === 'form.params' ? '八段底稿 form.params' : '声明 spec.fields' }}；字段详编（默认值/候选/说明）在右侧属性面板</div>
  </div>
</template>

<style scoped>
/* specFormShared 口径：与 SpecFormIdentity 等页签组件共用同一套字段/红标样式 */
.sf { display: flex; flex-direction: column; gap: 8px; }
.sf-sec { display: flex; align-items: center; gap: 8px; margin-top: 4px; font-size: 14px; font-weight: 600; color: var(--text); }
.sf-sec .el-button { margin-left: auto; }
.sf-count { font-size: 11px; font-weight: 400; color: var(--text-3); }
.sf-empty { padding: 10px 8px; font-size: 12px; color: var(--text-3); text-align: center; }
.sf-note { font-size: 11px; color: var(--text-3); }
.sf-grid-row { display: grid; grid-template-columns: 1.2fr 1.2fr 1.1fr 0.8fr auto auto; gap: 4px; align-items: center; padding: 2px; border: 1px solid transparent; border-radius: 6px; }
.sf-grid-row .el-input, .sf-grid-row .el-select { min-width: 0; }
.sf-out-desc { grid-column: span 3; }
.sf-acts { display: flex; gap: 2px; flex: none; }
.sf-mini { border: none; background: transparent; color: var(--text-3); font-size: 11px; cursor: pointer; padding: 2px 4px; border-radius: 4px; }
.sf-mini:hover { background: var(--bg, rgba(0, 0, 0, 0.06)); color: var(--text); }
.sf-mini:disabled { opacity: 0.35; cursor: default; }
.sf-mini-danger:hover { color: var(--danger, #f56c6c); }
.sf-bad :deep(.el-input__wrapper), .sf-bad :deep(.el-textarea__inner) { box-shadow: 0 0 0 1px var(--danger, #f56c6c) inset; }
.sf-bad-border { border-color: var(--danger, #f56c6c); }
</style>

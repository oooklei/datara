<script setup lang="ts">
/**
 * Task 6（方案§2.1/§2.6）表现页签：8 要素之 icon/color/badge + behaviors。
 * - badge：key + colorMap（值→颜色）行编辑，key 与 colorMap 皆空 = 未声明；
 * - behaviors 三段行编辑（枚举与 componentSpec.ts normBehaviors 白名单严格一致）：
 *   prefillFromUpstream.from ∈ input.table|input.columns|input.datasource；
 *   pick.picker ∈ table|column|cron|sshHost；onChange.action ∈ refreshOptions|resetFields|prefill。
 * 数据流单向：编辑组装分片经 patch 上抛宿主（FieldsState.decl），本组件无本地镜像；
 * 删光行为行 = behaviors 未声明（缺位键不落 JSON）。
 * 打字即校验：violations 由宿主 validateSpecPureData 下发（icon/color/badge/behaviors 前缀红标）。
 */
import { computed } from 'vue'
import type { SpecViolation } from '../../services/componentSpec'
import { ONCHANGE_ACTION_VALUES, PREFILL_FROM_VALUES, PICKER_VALUES, REMOTE_OPTION_SOURCE_VALUES } from '../../services/componentSpec'
import type { DeclBadge, DeclBehaviors } from '../../views/meta/pageDesigner/fields/fieldsModel'

const props = defineProps<{
  icon: string
  color: string
  badge?: DeclBadge
  behaviors?: DeclBehaviors
  violations: SpecViolation[]
}>()
const emit = defineEmits<{ (e: 'patch', p: Partial<{ icon: string; color: string; badge?: DeclBadge; behaviors?: DeclBehaviors }>): void }>()

/* 行为枚举值域单一源（审查修复）：值集来自 componentSpec 导出数组（与 normalizeSpec.normBehaviors
 * 白名单同源），本组件只维护中文 label 映射——消灭「白名单 Set vs 本地下拉枚举」两处同步漂移 */
const ACTION_LABEL: Record<string, string> = {
  refreshOptions: '刷新候选 refreshOptions',
  resetFields: '重置字段 resetFields',
  prefill: '预填 prefill',
}
const FROM_LABEL: Record<string, string> = {
  'input.table': '上游表 input.table',
  'input.columns': '上游列 input.columns',
  'input.datasource': '上游数据源 input.datasource',
}
const PICKER_LABEL: Record<string, string> = {
  table: '选表 table', column: '选列 column', cron: 'Cron 表达式', sshHost: 'SSH 主机',
}
const ONCHANGE_ACTIONS = ONCHANGE_ACTION_VALUES.map((value) => ({ value, label: ACTION_LABEL[value] ?? value }))
const PREFILL_FROMS = PREFILL_FROM_VALUES.map((value) => ({ value, label: FROM_LABEL[value] ?? value }))
const PICKERS = PICKER_VALUES.map((value) => ({ value, label: PICKER_LABEL[value] ?? value }))
const REMOTE_LABEL: Record<string, string> = {
  'datasource.tree': '数据源库表树',
  'datasource.topics': 'Kafka Topic',
  'runtime.nodes': '运行时节点',
}
const REMOTES = REMOTE_OPTION_SOURCE_VALUES.map((value) => ({ value, label: REMOTE_LABEL[value] ?? value }))

const badge = computed<DeclBadge | null>(() => props.badge ?? null)
const colorEntries = computed<[string, string][]>(() => Object.entries(badge.value?.colorMap ?? {}))
const onChangeRows = computed(() => props.behaviors?.onChange ?? [])
const prefillRows = computed(() => props.behaviors?.prefillFromUpstream ?? [])
const pickRows = computed(() => props.behaviors?.pick ?? [])

function bad(prefix: string): boolean {
  return props.violations.some((v) => v.path === prefix || v.path.startsWith(`${prefix}.`) || v.path.startsWith(`${prefix}[`))
}

/** badge 编辑：key/colorMap 任一有值即落声明，全空 = 未声明 */
function patchBadge(p: Partial<DeclBadge>): void {
  const key = 'key' in p ? (p.key as string) : (badge.value?.key ?? '')
  const colorMap = 'colorMap' in p ? (p.colorMap as Record<string, string>) : (badge.value?.colorMap ?? {})
  const next = key || Object.keys(colorMap).length ? { key, colorMap } : undefined
  emit('patch', { badge: next })
}
/** colorMap 编辑（审查修复）：改键时原值随行迁移（v 为该行现值），新键允许空串中间态（不回退旧键，
 * 否则清空键准备输入新键时会被旧键顶回无法续输）；重复键经 Object.fromEntries 静默合并——后写覆盖先写 */
function setMapValue(i: number, k: string, v: string): void {
  const entries = colorEntries.value.map(([ek, ev], xi) => (xi === i ? ([k, v] as [string, string]) : [ek, ev]))
  patchBadge({ colorMap: Object.fromEntries(entries) })
}
function addMapValue(): void {
  patchBadge({ colorMap: { ...badge.value?.colorMap, '': '#1677ff' } })
}
function removeMapValue(i: number): void {
  patchBadge({ colorMap: Object.fromEntries(colorEntries.value.filter((_, xi) => xi !== i)) })
}

/** behaviors 编辑：组装后整体上抛；三段全空 = 未声明 */
function emitBehaviors(p: Partial<NonNullable<DeclBehaviors>>): void {
  const next: DeclBehaviors = { ...(props.behaviors ?? {}), ...p }
  const cleaned: DeclBehaviors = {}
  if (next.onChange?.length) cleaned.onChange = next.onChange
  if (next.prefillFromUpstream?.length) cleaned.prefillFromUpstream = next.prefillFromUpstream
  if (next.pick?.length) cleaned.pick = next.pick
  emit('patch', { behaviors: Object.keys(cleaned).length ? cleaned : undefined })
}
function setOnChange(i: number, patch: Partial<NonNullable<DeclBehaviors['onChange']>[number]>): void {
  emitBehaviors({ onChange: onChangeRows.value.map((o, xi) => (xi === i ? { ...o, ...patch } : o)) })
}
function addOnChange(): void {
  emitBehaviors({ onChange: [...onChangeRows.value, { field: '', action: 'refreshOptions' }] })
}
function removeOnChange(i: number): void {
  emitBehaviors({ onChange: onChangeRows.value.filter((_, xi) => xi !== i) })
}
function setPrefill(i: number, patch: Partial<NonNullable<DeclBehaviors['prefillFromUpstream']>[number]>): void {
  emitBehaviors({ prefillFromUpstream: prefillRows.value.map((o, xi) => (xi === i ? { ...o, ...patch } : o)) })
}
function addPrefill(): void {
  emitBehaviors({ prefillFromUpstream: [...prefillRows.value, { field: '', from: 'input.table' }] })
}
function removePrefill(i: number): void {
  emitBehaviors({ prefillFromUpstream: prefillRows.value.filter((_, xi) => xi !== i) })
}
function setPick(i: number, patch: Partial<NonNullable<DeclBehaviors['pick']>[number]>): void {
  emitBehaviors({ pick: pickRows.value.map((o, xi) => (xi === i ? { ...o, ...patch } : o)) })
}
function addPick(): void {
  emitBehaviors({ pick: [...pickRows.value, { field: '', picker: 'table' }] })
}
function removePick(i: number): void {
  emitBehaviors({ pick: pickRows.value.filter((_, xi) => xi !== i) })
}
/** onChange.target：逗号分隔字符串 ↔ 字符串数组 */
function targetText(t: string[] | undefined): string {
  return (t ?? []).join(',')
}
function onTargetInput(i: number, v: string): void {
  setOnChange(i, { target: v.split(',').map((s) => s.trim()).filter(Boolean) })
}
</script>

<template>
  <div class="sf" data-testid="sf-visual">
    <label class="sf-field">
      <span>图标</span>
      <el-input
        :model-value="icon" placeholder="如 ⬢ / ⊞（palette 呈现，缺 icon 不满足拖入门槛）"
        :class="{ 'sf-bad': bad('icon') }" data-testid="sf-vi-icon"
        @update:model-value="emit('patch', { icon: $event })"
      />
    </label>
    <label class="sf-field">
      <span>颜色</span>
      <el-input
        :model-value="color" placeholder="如 #1677ff"
        :class="{ 'sf-bad': bad('color') }" @update:model-value="emit('patch', { color: $event })"
      />
    </label>

    <div class="sf-sec">状态徽标</div>
    <div class="sf-note">按字段值着色的节点徽标（key=字段名，colorMap=值→颜色）；全空 = 未声明</div>
    <label class="sf-field">
      <span>字段</span>
      <el-input
        :model-value="badge?.key ?? ''" placeholder="徽标取值字段（如 state）"
        :class="{ 'sf-bad': bad('badge.key') }" @update:model-value="patchBadge({ key: $event })"
      />
    </label>
    <div v-for="([k, v], i) in colorEntries" :key="i" class="sf-row">
      <el-input :model-value="k" placeholder="值" @update:model-value="setMapValue(i, $event, v)" />
      <el-input :model-value="v" placeholder="颜色" @update:model-value="setMapValue(i, k, $event)" />
      <span class="sf-dot" :style="{ background: v }" />
      <button type="button" class="sf-mini sf-mini-danger" title="删除映射" @click="removeMapValue(i)">删</button>
    </div>
    <el-button size="small" plain data-testid="sf-vi-map-add" @click="addMapValue">加颜色映射</el-button>

    <div class="sf-sec">声明式行为</div>
    <div class="sf-note">三段均空 = 未声明；枚举与 componentSpec 白名单严格一致</div>

    <div class="sf-sub">预填上游 prefillFromUpstream</div>
    <div v-for="(o, i) in prefillRows" :key="`pf${i}`" class="sf-row" :class="{ 'sf-bad-border': bad(`behaviors.prefillFromUpstream[${i}]`) }">
      <el-input :model-value="o.field" placeholder="字段 key" @update:model-value="setPrefill(i, { field: $event })" />
      <el-select :model-value="o.from" @update:model-value="setPrefill(i, { from: $event as 'input.table' })">
        <el-option v-for="f in PREFILL_FROMS" :key="f.value" :label="f.label" :value="f.value" />
      </el-select>
      <button type="button" class="sf-mini sf-mini-danger" title="删除" @click="removePrefill(i)">删</button>
    </div>
    <el-button size="small" plain data-testid="sf-vi-prefill-add" @click="addPrefill">加预填</el-button>

    <div class="sf-sub">拾取器 pick</div>
    <div v-for="(o, i) in pickRows" :key="`pk${i}`" class="sf-row" :class="{ 'sf-bad-border': bad(`behaviors.pick[${i}]`) }">
      <el-input :model-value="o.field" placeholder="字段 key" @update:model-value="setPick(i, { field: $event })" />
      <el-select :model-value="o.picker" @update:model-value="setPick(i, { picker: $event as 'table' })">
        <el-option v-for="p in PICKERS" :key="p.value" :label="p.label" :value="p.value" />
      </el-select>
      <button type="button" class="sf-mini sf-mini-danger" title="删除" @click="removePick(i)">删</button>
    </div>
    <el-button size="small" plain data-testid="sf-vi-pick-add" @click="addPick">加拾取器</el-button>

    <div class="sf-sub">联动 onChange</div>
    <div v-for="(o, i) in onChangeRows" :key="`oc${i}`" class="sf-row sf-row-wide" :class="{ 'sf-bad-border': bad(`behaviors.onChange[${i}]`) }">
      <el-input :model-value="o.field" placeholder="触发字段 key" @update:model-value="setOnChange(i, { field: $event })" />
      <el-select :model-value="o.action" @update:model-value="setOnChange(i, { action: $event as 'refreshOptions' })">
        <el-option v-for="a in ONCHANGE_ACTIONS" :key="a.value" :label="a.label" :value="a.value" />
      </el-select>
      <el-input
        :model-value="targetText(o.target)" placeholder="目标字段（逗号分隔，可空）"
        @update:model-value="onTargetInput(i, $event)"
      />
      <el-select :model-value="o.remote ?? ''" placeholder="刷新来源（可空）" clearable @update:model-value="setOnChange(i, { remote: $event || undefined })">
        <el-option v-for="remote in REMOTES" :key="remote.value" :label="remote.label" :value="remote.value" />
      </el-select>
      <button type="button" class="sf-mini sf-mini-danger" title="删除" @click="removeOnChange(i)">删</button>
    </div>
    <el-button size="small" plain data-testid="sf-vi-onchange-add" @click="addOnChange">加联动</el-button>
  </div>
</template>

<style scoped>
/* specFormShared 口径：与 SpecFormIdentity 等页签组件共用同一套字段/红标样式 */
.sf { display: flex; flex-direction: column; gap: 8px; }
.sf-sec { font-size: 14px; font-weight: 600; color: var(--text); margin-top: 8px; }
.sf-sub { font-size: 12px; font-weight: 600; color: var(--text-2); margin-top: 4px; }
.sf-note { font-size: 11px; color: var(--text-3); margin-top: -4px; }
.sf-field { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-2); }
.sf-field > span { flex: none; width: 52px; }
.sf-field .el-input, .sf-field .el-select { flex: 1; min-width: 0; }
.sf-row { display: grid; grid-template-columns: 1fr 1.4fr auto; gap: 4px; align-items: center; padding: 2px; border: 1px solid transparent; border-radius: 6px; }
.sf-row-wide { grid-template-columns: 1fr 1.2fr 1fr 1fr auto; }
.sf-row .el-input, .sf-row .el-select { min-width: 0; }
.sf-dot { width: 14px; height: 14px; border-radius: 3px; border: 1px solid var(--border); flex: none; }
.sf-mini { border: none; background: transparent; color: var(--text-3); font-size: 11px; cursor: pointer; padding: 2px 4px; border-radius: 4px; }
.sf-mini:hover { background: var(--bg, rgba(0, 0, 0, 0.06)); color: var(--text); }
.sf-mini-danger:hover { color: var(--danger, #f56c6c); }
.sf-bad :deep(.el-input__wrapper), .sf-bad :deep(.el-textarea__inner) { box-shadow: 0 0 0 1px var(--danger, #f56c6c) inset; }
.sf-bad-border { border-color: var(--danger, #f56c6c); }
</style>

<script lang="ts">
/**
 * 下拉候选 → BindingRef kind 映射（导出供测试复用）：
 * ds:{id} → query（datasourceId）；$wf./$param./$system. → variable（path）；
 * 其余 → static。fallback 恒为槽默认文案（placeholder 即默认值口径）。
 */
import type { BindingRef } from '../designerModel'
export function bindingOf(value: string, fallback: string): BindingRef {
  if (value.startsWith('ds:')) {
    const id = Number(value.slice(3))
    return { kind: 'query', datasourceId: Number.isFinite(id) ? id : undefined, fallback }
  }
  if (value.startsWith('$wf.') || value.startsWith('$param.') || value.startsWith('$system.')) {
    return { kind: 'variable', path: value, fallback }
  }
  return { kind: 'static', fallback }
}
</script>

<script setup lang="ts">
/**
 * 组件页面设计器 Task 12：右侧属性面板。
 * - 未选中 → 画布段（宽/高钳制与 CANVAS_W/H 同口径、背景填充、背景图 URL）→ updateCanvas patch
 * - 选中 → 布局（rect x/y/w/h）/ 样式（填充/圆角/字号/字色）→ updateWidget patch；
 *   数据绑定段按 SLOTS 槽位清单（dataset=数据集入口 / scalar=值与默认值语义），
 *   每槽：候选下拉（candidatesFor，allowClear）+「手动输入」开关；
 *   手动输入确认/blur → resolveFallback(placeholder, input) 落 fallback（空值落 placeholder 文案）。
 * 布局/样式输入为受控合成 patch（以当前值合成完整对象，合并归宿主），无本地镜像状态。
 */
import { computed, ref } from 'vue'
import { CANVAS_H, CANVAS_W, type PageDSL, type Rect, type WidgetNode } from '../designerModel'
import { candidatesFor, resolveFallback, type ResourceCatalog, type SlotType } from '../bindingCatalog'
import { widgetTemplate } from '../templates'

interface SlotSpec { key: string; label: string; slot: SlotType }

/** 槽位清单（按 kind）：无槽位的纯装饰（divider/spacer/card/tabs/collapse/grid-row/rich-text/icon/switch/slider/radio/checkbox/cascader/upload）不渲染绑定段 */
const SLOTS: Record<string, SlotSpec[]> = {
  table: [{ key: 'data', label: '数据源', slot: 'dataset' }],
  list: [{ key: 'data', label: '数据源', slot: 'dataset' }],
  tree: [{ key: 'data', label: '数据源', slot: 'dataset' }],
  'query-result': [{ key: 'data', label: '数据源', slot: 'dataset' }],
  'chart-bar': [{ key: 'data', label: '数据', slot: 'dataset' }],
  'chart-line': [{ key: 'data', label: '数据', slot: 'dataset' }],
  'chart-pie': [{ key: 'data', label: '数据', slot: 'dataset' }],
  'chart-area': [{ key: 'data', label: '数据', slot: 'dataset' }],
  'chart-gauge': [{ key: 'data', label: '数据', slot: 'dataset' }],
  'chart-scatter': [{ key: 'data', label: '数据', slot: 'dataset' }],
  image: [{ key: 'url', label: '图片地址', slot: 'scalar' }],
  'sys-status': [{ key: 'value', label: '状态值', slot: 'scalar' }],
  'meta-field': [{ key: 'value', label: '字段值', slot: 'scalar' }],
  'var-label': [{ key: 'value', label: '变量值', slot: 'scalar' }],
  statistic: [{ key: 'value', label: '指标值', slot: 'scalar' }],
  text: [{ key: 'value', label: '文本值', slot: 'scalar' }],
  heading: [{ key: 'value', label: '文本值', slot: 'scalar' }],
  badge: [{ key: 'value', label: '文本值', slot: 'scalar' }],
  link: [{ key: 'value', label: '链接值', slot: 'scalar' }],
  button: [{ key: 'value', label: '按钮文案', slot: 'scalar' }],
  input: [{ key: 'value', label: '默认值', slot: 'scalar' }],
  number: [{ key: 'value', label: '默认值', slot: 'scalar' }],
  select: [{ key: 'value', label: '默认值', slot: 'scalar' }],
  date: [{ key: 'value', label: '默认值', slot: 'scalar' }],
  'date-range': [{ key: 'value', label: '默认值', slot: 'scalar' }],
  textarea: [{ key: 'value', label: '默认值', slot: 'scalar' }],
}

const props = defineProps<{ page: PageDSL; selectedId?: string; catalog: ResourceCatalog }>()
const emit = defineEmits<{
  updateWidget: [id: string, patch: Record<string, unknown>]
  updateCanvas: [patch: Record<string, unknown>]
}>()

const sel = computed<WidgetNode | null>(() => props.page.widgets.find((w) => w.id === props.selectedId) ?? null)
const slots = computed<SlotSpec[]>(() => (sel.value ? SLOTS[sel.value.kind] ?? [] : []))

/** 槽默认文案（placeholder 即默认值）：模板 props 语义字段优先，widget 当前 props 兜底 */
function slotPlaceholder(w: WidgetNode, s: SlotSpec): string {
  const tp = widgetTemplate(w.kind)?.props ?? {}
  if (s.slot === 'dataset') return typeof tp.emptyText === 'string' && tp.emptyText !== '' ? tp.emptyText : '数据集'
  for (const k of ['text', 'fallback', 'value', 'placeholder', 'src']) {
    if (s.key === 'url' && k === 'value') continue
    const v = tp[k]
    if (typeof v === 'string' && v !== '') return v
  }
  const cur = w.props[s.key]
  return typeof cur === 'string' && cur !== '' ? cur : `${w.kind} 值`
}

const candidates = (s: SlotSpec) => candidatesFor(s.slot, props.catalog)

/** 当前绑定在下拉的回显值（query → ds:{id}；variable → path） */
function currentBindValue(s: SlotSpec): string {
  const b = sel.value?.bindings[s.key]
  if (!b) return ''
  if (b.kind === 'query') return b.datasourceId != null ? `ds:${b.datasourceId}` : ''
  if (b.kind === 'variable') return b.path ?? ''
  return ''
}

/* 下拉选择：kind 由候选来源映射（bindingOf）；清空（allowClear）→ 静态默认值 */
function onPick(s: SlotSpec, value: unknown) {
  const w = sel.value
  if (!w) return
  const fb = slotPlaceholder(w, s)
  const v = value == null || value === '' ? undefined : String(value)
  emit('updateWidget', w.id, { bindings: { [s.key]: v ? bindingOf(v, fb) : { kind: 'static', fallback: fb } } })
}

/* 手动输入（static）：确认/blur → resolveFallback 落值（空值落 placeholder 文案） */
const manualOpen = ref<Set<string>>(new Set())
const manualText = ref('')
const manualKey = (s: SlotSpec) => (sel.value ? `${sel.value.id}:${s.key}` : '')
const isManual = (s: SlotSpec) => manualOpen.value.has(manualKey(s))
function toggleManual(s: SlotSpec, on: unknown) {
  const k = manualKey(s)
  if (!k) return
  if (on) manualOpen.value.add(k)
  else manualOpen.value.delete(k)
  manualText.value = ''
}
function confirmManual(s: SlotSpec) {
  const w = sel.value
  if (!w || !manualOpen.value.has(`${w.id}:${s.key}`)) return
  const fb = resolveFallback(slotPlaceholder(w, s), manualText.value)
  emit('updateWidget', w.id, { bindings: { [s.key]: { kind: 'static', fallback: fb } } })
  manualText.value = ''
}

/* 布局/样式/画布受控 patch（handler 显式 unknown 入参，模板零内联箭头） */
function patchRect(part: Partial<Rect>) {
  const w = sel.value
  if (w) emit('updateWidget', w.id, { rect: { ...w.rect, ...part } })
}
function patchStyle(part: Record<string, string | number>) {
  const w = sel.value
  if (w) emit('updateWidget', w.id, { style: { ...w.style, ...part } })
}
const patchCanvas = (part: Record<string, unknown>) => emit('updateCanvas', part)
const clampW = (v: number) => Math.min(CANVAS_W.max, Math.max(CANVAS_W.min, v))
const clampH = (v: number) => Math.min(CANVAS_H.max, Math.max(CANVAS_H.min, v))
const num = (v: unknown) => Number(v)
const setCanvasW = (v: unknown) => patchCanvas({ width: clampW(num(v)) })
const setCanvasH = (v: unknown) => patchCanvas({ height: clampH(num(v)) })
const setCanvasImage = (v: unknown) => patchCanvas({ background: { image: v ? String(v) : undefined } })
const setRectKey = (k: 'x' | 'y' | 'w' | 'h') => (v: unknown) => patchRect({ [k]: num(v) })
const setStyleKey = (k: string) => (v: unknown) => patchStyle({ [k]: num(v) })
const onCanvasFill = (e: Event) => patchCanvas({ background: { fill: (e.target as HTMLInputElement).value } })
const onStyleColor = (key: string) => (e: Event) => patchStyle({ [key]: (e.target as HTMLInputElement).value })
</script>

<template>
  <aside class="pd-insp">
    <!-- 画布段（未选中） -->
    <template v-if="!sel">
      <div class="pd-insp-title">画布</div>
      <div class="pd-insp-grid">
        <label class="pd-insp-field"><span>宽度</span><el-input-number :model-value="page.canvas.width" @update:model-value="setCanvasW" /></label>
        <label class="pd-insp-field"><span>高度</span><el-input-number :model-value="page.canvas.height" @update:model-value="setCanvasH" /></label>
        <label class="pd-insp-field"><span>背景填充</span><input type="color" class="pd-insp-color" :value="page.canvas.background?.fill ?? '#ffffff'" @input="onCanvasFill" /></label>
        <label class="pd-insp-field pd-insp-field-wide"><span>背景图 URL</span><el-input :model-value="page.canvas.background?.image ?? ''" placeholder="https://…" @update:model-value="setCanvasImage" /></label>
      </div>
    </template>

    <!-- widget 段（选中）：布局 / 样式 / 数据绑定 -->
    <el-tabs v-else>
      <el-tab-pane label="布局" name="layout">
        <div class="pd-insp-grid">
          <label class="pd-insp-field"><span>X</span><el-input-number :model-value="sel.rect.x" @update:model-value="setRectKey('x')" /></label>
          <label class="pd-insp-field"><span>Y</span><el-input-number :model-value="sel.rect.y" @update:model-value="setRectKey('y')" /></label>
          <label class="pd-insp-field"><span>宽</span><el-input-number :model-value="sel.rect.w" :min="1" @update:model-value="setRectKey('w')" /></label>
          <label class="pd-insp-field"><span>高</span><el-input-number :model-value="sel.rect.h" :min="1" @update:model-value="setRectKey('h')" /></label>
        </div>
      </el-tab-pane>
      <el-tab-pane label="样式" name="style">
        <div class="pd-insp-grid">
          <label class="pd-insp-field"><span>填充色</span><input type="color" class="pd-insp-color" :value="String(sel.style.fill ?? '#ffffff')" @input="onStyleColor('fill')" /></label>
          <label class="pd-insp-field"><span>圆角</span><el-input-number :model-value="Number(sel.style.radius ?? 0)" :min="0" :max="48" @update:model-value="setStyleKey('radius')" /></label>
          <label class="pd-insp-field"><span>字号</span><el-input-number :model-value="Number(sel.style.fontSize ?? 13)" :min="10" :max="48" @update:model-value="setStyleKey('fontSize')" /></label>
          <label class="pd-insp-field"><span>字色</span><input type="color" class="pd-insp-color" :value="String(sel.style.color ?? '#1f2329')" @input="onStyleColor('color')" /></label>
        </div>
      </el-tab-pane>
      <el-tab-pane v-if="slots.length > 0" label="数据绑定" name="binding">
        <div v-for="s in slots" :key="s.key" class="pd-insp-slot">
          <div class="pd-insp-slot-head">
            <span class="pd-insp-slot-label">{{ s.label }}（{{ s.slot }}）</span>
            <span class="pd-insp-slot-manual">手动输入<el-switch :model-value="isManual(s)" @update:model-value="toggleManual(s, $event)" /></span>
          </div>
          <el-select
            v-if="!isManual(s)" :model-value="currentBindValue(s)" allow-clear
            placeholder="选择绑定候选" @update:model-value="onPick(s, $event)"
          >
            <el-option v-for="c in candidates(s)" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
          <div v-else class="pd-insp-manual">
            <el-input v-model="manualText" :placeholder="slotPlaceholder(sel, s)" @blur="confirmManual(s)" @keyup.enter="confirmManual(s)" />
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </aside>
</template>

<style scoped>
.pd-insp {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 12px;
  background: #ffffff;
  border-left: 1px solid #e5e6eb;
  box-sizing: border-box;
}
.pd-insp-title {
  margin: 4px 2px 12px;
  font-size: 14px;
  font-weight: 600;
  color: #1f2329;
}
.pd-insp-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.pd-insp-field {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #4e5969;
}
.pd-insp-field > span {
  flex: none;
  width: 48px;
}
.pd-insp-field-wide {
  grid-column: 1 / -1;
}
.pd-insp-field :deep(.el-input-number),
.pd-insp-field :deep(.el-input) {
  flex: 1;
  min-width: 0;
}
.pd-insp-color {
  flex: 1;
  min-width: 0;
  height: 26px;
  padding: 0;
  border: 1px solid #e5e6eb;
  border-radius: 6px;
  background: #ffffff;
  cursor: pointer;
}
.pd-insp-slot {
  margin-bottom: 12px;
}
.pd-insp-slot-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 12px;
  color: #1f2329;
}
.pd-insp-slot-manual {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  color: #86909c;
}
.pd-insp-manual {
  margin-top: 4px;
}
</style>

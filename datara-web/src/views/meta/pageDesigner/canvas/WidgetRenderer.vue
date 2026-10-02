<script setup lang="ts">
/**
 * 组件页面设计器 Task 11：widget 只读渲染分派（设计态骨架预览）。
 * 按 kind 分派：容器（children 递归）/文本/表单（disabled 骨架）/table/数据展示/图表(SVG)/绑定元素。
 * - 绝对定位 + style 映射（fill/radius/border/shadow/fontSize/color…），选中态主色描边
 * - 预览优先：preview 无 error 且有数据时 table/statistic/progress/绑定元素等吃真实数据，否则模板默认/空态
 * - 渲染异常兜底：onErrorCaptured 捕获 children 递归错误输出兜底卡片，不拖垮画布
 * 实现取原生元素 + SVG（零 UI 库依赖）：设计态只读骨架无需重型表格组件，jsdom/生产渲染均轻量稳定。
 */
import { computed, ref } from 'vue'
import type { WidgetNode } from '../designerModel'
import type { PreviewResult } from '../pageApi'

const props = defineProps<{ widget: WidgetNode; selected?: boolean; preview?: PreviewResult }>()
const emit = defineEmits<{
  select: []
  move: [dx: number, dy: number]
  resize: [dw: number, dh: number]
}>()

const broken = ref(false)
function onDescErr(): boolean {
  broken.value = true
  return false
}

const kind = computed(() => props.widget.kind)
const isContainer = computed(() => ['grid-row', 'card', 'tabs', 'collapse'].includes(kind.value))
const isChart = computed(() => kind.value.startsWith('chart-'))
const isBinding = computed(() => ['meta-field', 'var-label', 'query-result', 'sys-status'].includes(kind.value))

/* ---------- 定位与样式映射 ---------- */
const rootStyle = computed<Record<string, string>>(() => {
  const r = props.widget.rect
  const s = props.widget.style ?? {}
  const out: Record<string, string> = {
    left: `${r.x}px`,
    top: `${r.y}px`,
    width: `${r.w}px`,
    height: `${r.h}px`,
  }
  if (s.fill) out.background = String(s.fill)
  if (s.radius !== undefined && s.radius !== '') out.borderRadius = `${s.radius}px`
  if (s.border) out.border = String(s.border)
  if (s.shadow) out.boxShadow = String(s.shadow)
  if (s.fontSize) out.fontSize = `${s.fontSize}px`
  if (s.color) out.color = String(s.color)
  if (s.fontWeight) out.fontWeight = String(s.fontWeight)
  return out
})

/* ---------- 预览工具：无 error 且有数据才吃预览 ---------- */
const pvOk = computed(() => !!props.preview && !props.preview.error && props.preview.rows.length > 0)

/* ---------- 文本/绑定类取值 ---------- */
function firstCell(): string {
  const pv = props.preview
  return pvOk.value && pv!.rows[0].length > 0 ? String(pv!.rows[0][0]) : ''
}
const textVal = computed(() => firstCell() || String(props.widget.props.text ?? ''))
const bindVal = computed(() => {
  const v = firstCell()
  if (v !== '') return v
  const p = props.widget.props
  return String(p.fallback ?? p.text ?? '')
})
const bindColor = computed(() => String(props.widget.props.color ?? '#1677ff'))

/* ---------- 容器类 ---------- */
const tabList = computed<string[]>(() => (props.widget.props.tabs as string[]) ?? [])
const panelList = computed<{ title: string }[]>(() => (props.widget.props.panels as { title: string }[]) ?? [])
const gridCols = computed(() => Number(props.widget.props.columns ?? 2))

/* ---------- 表单类 ---------- */
const formPh = computed(() => String(props.widget.props.placeholder ?? ''))
const formLabel = computed(() => String(props.widget.props.label ?? ''))
const switchOn = computed(() => !!props.widget.props.checked)
const sliderPct = computed(() => {
  const min = Number(props.widget.props.min ?? 0)
  const max = Number(props.widget.props.max ?? 100)
  const v = Number(props.widget.props.value ?? 0)
  return max > min ? Math.min(100, Math.max(0, ((v - min) / (max - min)) * 100)) : 0
})
const radioOpts = computed<string[]>(() => (props.widget.props.options as string[]) ?? [])
const radioVal = computed(() => props.widget.props.value)
const isCbChecked = (opt: string) => Array.isArray(radioVal.value) && (radioVal.value as unknown[]).includes(opt)

/* ---------- table ---------- */
interface TCol { title: string; dataIndex: string }
const tplCols = computed<TCol[]>(() => (props.widget.props.columns as TCol[]) ?? [])
const hasData = computed(() => pvOk.value)
const tableCols = computed<TCol[]>(() =>
  hasData.value
    ? props.preview!.columns.map((c, i) => ({ title: c, dataIndex: String(i) }))
    : tplCols.value,
)
const tableRows = computed<Record<string, string>[]>(() =>
  hasData.value
    ? props.preview!.rows.map((r) => Object.fromEntries(r.map((v, i) => [String(i), String(v)])))
    : [],
)
const tableEmpty = computed(() => String(props.widget.props.emptyText ?? '暂无数据'))

/* ---------- 数据展示类 ---------- */
const statVal = computed(() => firstCell() || String(props.widget.props.value ?? '0'))
const statTitle = computed(() => String(props.widget.props.title ?? ''))
const progressPct = computed(() => {
  const pvNum = Number(firstCell())
  return Number.isFinite(pvNum) && firstCell() !== '' ? Math.min(100, Math.max(0, pvNum)) : Number(props.widget.props.percent ?? 0)
})
const descItems = computed<{ label: string; value: string }[]>(() => {
  const pv = props.preview
  if (pvOk.value) return pv!.columns.map((c, i) => ({ label: c, value: String(pv!.rows[0][i] ?? '-') }))
  return ((props.widget.props.items as { label: string; value: string }[]) ?? []).map((i) => ({ label: String(i.label), value: String(i.value) }))
})
const timelineItems = computed<string[]>(() => {
  if (pvOk.value) return props.preview!.rows.map((r) => r.join(' / '))
  return ((props.widget.props.items as string[]) ?? []).map(String)
})
interface TreeNode { title: string; children?: TreeNode[] }
const treeData = computed<TreeNode[]>(() => (props.widget.props.treeData as TreeNode[]) ?? [])
const listEmpty = computed(() => String(props.widget.props.emptyText ?? '暂无数据'))

/* ---------- 图表（SVG） ---------- */
const seriesType = computed(() => String(props.widget.props.seriesType ?? kind.value.slice(6)))
const chartEmpty = computed(() => String(props.widget.props.emptyText ?? '暂无数据'))
/** 预览数值行驱动形态（无数据 → 演示灰调形态） */
const chartVals = computed<number[]>(() => {
  const pv = props.preview
  if (!pvOk.value) return []
  const nums = pv!.rows.map((r) => Number(r[0])).filter((n) => Number.isFinite(n))
  return nums.length > 0 ? nums : []
})
const VB = { w: 100, h: 60 }
const barRects = computed(() => {
  const vals = chartVals.value.length > 0 ? chartVals.value : [0.5, 0.8, 0.35]
  const max = Math.max(...vals, 1e-9)
  const step = VB.w / vals.length
  return vals.map((v, i) => {
    const h = Math.max(2, (v / max) * (VB.h - 10))
    return { x: i * step + step * 0.18, y: VB.h - h, w: step * 0.64, h, demo: chartVals.value.length === 0 }
  })
})
const linePoints = computed(() => {
  const vals = chartVals.value.length > 0 ? chartVals.value : [0.3, 0.6, 0.45, 0.8]
  const max = Math.max(...vals, 1e-9)
  const step = VB.w / Math.max(1, vals.length - 1)
  return vals.map((v, i) => `${i * step},${VB.h - 6 - (v / max) * (VB.h - 14)}`).join(' ')
})
const pieSegs = computed(() => {
  const vals = chartVals.value.length > 0 ? chartVals.value : [1]
  const sum = vals.reduce((a, b) => a + b, 0) || 1
  const C = 2 * Math.PI * 20
  let acc = 0
  return vals.map((v, i) => {
    const len = (v / sum) * C
    const seg = { dasharray: `${len} ${C - len}`, offset: `${C * 0.25 - acc}`, demo: chartVals.value.length === 0, i }
    acc += len
    return seg
  })
})
const gaugePct = computed(() => {
  const v = Number(firstCell() || (props.widget.props.value ?? 0))
  return Math.min(100, Math.max(0, Number.isFinite(v) ? v : 0))
})
const gaugeArc = computed(() => {
  const C = Math.PI * 30 // 半圆弧长（r=30）
  return { bg: `30 ${C}`, fg: `${(gaugePct.value / 100) * C} ${C}` }
})
const scatterPts = computed(() => {
  if (!pvOk.value) return [{ x: 20, y: 40, demo: true }, { x: 45, y: 22, demo: true }, { x: 70, y: 48, demo: true }]
  const pv = props.preview!
  const nums = pv.rows.map((r) => ({ x: Number(r[0]), y: Number(r[1] ?? r[0]) })).filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
  const xs = nums.map((p) => p.x)
  const ys = nums.map((p) => p.y)
  const xmin = Math.min(...xs, 0)
  const xmax = Math.max(...xs, 1)
  const ymin = Math.min(...ys, 0)
  const ymax = Math.max(...ys, 1)
  return nums.map((p) => ({
    x: 8 + ((p.x - xmin) / (xmax - xmin || 1)) * (VB.w - 16),
    y: VB.h - 8 - ((p.y - ymin) / (ymax - ymin || 1)) * (VB.h - 16),
    demo: false,
  }))
})

/* ---------- widget 级 resize 手柄（右下 grip，emit 相对位移） ---------- */
let rsx = 0
let rsy = 0
function startResize(e: MouseEvent) {
  rsx = e.clientX
  rsy = e.clientY
  window.addEventListener('mousemove', onResizeMove)
  window.addEventListener('mouseup', stopResize)
  e.preventDefault()
  e.stopPropagation()
}
function onResizeMove(e: MouseEvent) {
  emit('resize', e.clientX - rsx, e.clientY - rsy)
  rsx = e.clientX
  rsy = e.clientY
}
function stopResize() {
  window.removeEventListener('mousemove', onResizeMove)
  window.removeEventListener('mouseup', stopResize)
}
</script>

<template>
  <div
    class="pd-w-root" :class="{ 'is-selected': selected, [`pd-wk-${widget.kind}`]: true }" :style="rootStyle"
    :data-kind="widget.kind" @click.stop="$emit('select')"
  >
    <div v-if="broken" class="pd-w-broken">渲染异常：{{ widget.kind }}</div>

    <!-- 容器类：children 递归 -->
    <template v-else-if="isContainer">
      <div v-if="widget.kind === 'card'" class="pd-w-card">
        <div class="pd-w-card-title">{{ widget.props.title }}</div>
        <div class="pd-w-kids">
          <WidgetRenderer v-for="c in widget.children ?? []" :key="c.id" :widget="c" :selected="false" @select="$emit('select')" />
        </div>
      </div>
      <div v-else-if="widget.kind === 'grid-row'" class="pd-w-grid" :style="{ gridTemplateColumns: `repeat(${gridCols}, 1fr)` }">
        <WidgetRenderer v-for="c in widget.children ?? []" :key="c.id" :widget="c" :selected="false" @select="$emit('select')" />
      </div>
      <div v-else-if="widget.kind === 'tabs'" class="pd-w-tabs">
        <div class="pd-w-tabs-head">
          <span v-for="(t, i) in tabList" :key="t" class="pd-w-tab" :class="{ 'is-active': i === 0 }">{{ t }}</span>
        </div>
        <div class="pd-w-kids">
          <WidgetRenderer v-for="c in widget.children ?? []" :key="c.id" :widget="c" :selected="false" @select="$emit('select')" />
        </div>
      </div>
      <div v-else class="pd-w-collapse">
        <div v-for="p in panelList" :key="p.title" class="pd-w-collapse-item">
          <div class="pd-w-collapse-title">{{ p.title }}</div>
          <div class="pd-w-kids">
            <WidgetRenderer v-for="c in widget.children ?? []" :key="c.id" :widget="c" :selected="false" @select="$emit('select')" />
          </div>
        </div>
      </div>
    </template>

    <!-- 基础元素 -->
    <span v-else-if="kind === 'text'" class="pd-w-text">{{ textVal }}</span>
    <div v-else-if="kind === 'heading'" class="pd-w-heading">{{ textVal }}</div>
    <a v-else-if="kind === 'link'" class="pd-w-link" href="javascript:void(0)">{{ textVal }}</a>
    <span v-else-if="kind === 'badge'" class="pd-w-badge" :style="{ background: bindColor }">{{ textVal }}</span>
    <button v-else-if="kind === 'button'" class="pd-w-btn" type="button" disabled>{{ textVal }}</button>
    <span v-else-if="kind === 'icon'" class="pd-w-ico">◆</span>
    <img v-else-if="kind === 'image'" class="pd-w-img" :src="String(widget.props.src ?? '')" alt="插图" />
    <div v-else-if="kind === 'rich-text'" class="pd-w-rich" v-html="String(widget.props.html ?? '')" />
    <div v-else-if="kind === 'divider'" class="pd-w-divider" :style="{ background: String(widget.style?.color ?? '#f0f0f0') }" />
    <div v-else-if="kind === 'spacer'" class="pd-w-spacer" />

    <!-- 表单类：disabled 骨架 -->
    <label v-else-if="['input', 'number', 'textarea'].includes(kind)" class="pd-w-field">
      <span v-if="formLabel" class="pd-w-field-label">{{ formLabel }}</span>
      <textarea v-if="kind === 'textarea'" class="pd-w-textarea" disabled :placeholder="formPh" />
      <input v-else class="pd-w-input" :type="kind === 'number' ? 'number' : 'text'" disabled :placeholder="formPh" />
    </label>
    <label v-else-if="['select', 'date', 'date-range', 'cascader'].includes(kind)" class="pd-w-field">
      <span v-if="formLabel" class="pd-w-field-label">{{ formLabel }}</span>
      <div class="pd-w-select"><span class="pd-w-select-ph">{{ formPh || '请选择' }}</span><span class="pd-w-caret">▾</span></div>
    </label>
    <label v-else-if="kind === 'switch'" class="pd-w-field">
      <span class="pd-w-switch" :class="{ 'is-on': switchOn }" /><span v-if="formLabel" class="pd-w-field-label">{{ formLabel }}</span>
    </label>
    <div v-else-if="kind === 'slider'" class="pd-w-slider"><div class="pd-w-slider-fill" :style="{ width: `${sliderPct}%` }" /></div>
    <span v-else-if="kind === 'radio'" class="pd-w-opts">
      <label v-for="o in radioOpts" :key="o" class="pd-w-opt"><input type="radio" disabled :checked="radioVal === o" />{{ o }}</label>
    </span>
    <span v-else-if="kind === 'checkbox'" class="pd-w-opts">
      <label v-for="o in radioOpts" :key="o" class="pd-w-opt"><input type="checkbox" disabled :checked="isCbChecked(o)" />{{ o }}</label>
    </span>
    <div v-else-if="kind === 'upload'" class="pd-w-upload">＋ {{ widget.props.label ?? '上传附件' }}</div>

    <!-- table -->
    <table v-else-if="kind === 'table'" class="pd-w-table">
      <thead>
        <tr><th v-for="c in tableCols" :key="c.dataIndex">{{ c.title }}</th></tr>
      </thead>
      <tbody>
        <tr v-if="!hasData"><td class="pd-w-table-empty" :colspan="Math.max(1, tableCols.length)">{{ tableEmpty }}</td></tr>
        <tr v-for="(r, ri) in tableRows" v-else :key="ri">
          <td v-for="c in tableCols" :key="c.dataIndex">{{ r[c.dataIndex] }}</td>
        </tr>
      </tbody>
    </table>

    <!-- 数据展示 -->
    <div v-else-if="kind === 'statistic'" class="pd-w-stat">
      <div v-if="statTitle" class="pd-w-stat-title">{{ statTitle }}</div>
      <div class="pd-w-stat-value">{{ statVal }}</div>
    </div>
    <div v-else-if="kind === 'progress'" class="pd-w-progress"><div class="pd-w-progress-fill" :style="{ width: `${progressPct}%` }" /></div>
    <div v-else-if="kind === 'descriptions'" class="pd-w-desc">
      <div v-for="it in descItems" :key="it.label" class="pd-w-desc-row">
        <span class="pd-w-desc-label">{{ it.label }}</span><span class="pd-w-desc-value">{{ it.value }}</span>
      </div>
    </div>
    <ul v-else-if="kind === 'timeline'" class="pd-w-timeline">
      <li v-for="(t, i) in timelineItems" :key="i">{{ t }}</li>
    </ul>
    <div v-else-if="kind === 'list'" class="pd-w-list">
      <div v-if="pvOk" v-for="(r, i) in preview!.rows" :key="i" class="pd-w-list-item">{{ r.join(' · ') }}</div>
      <div v-else class="pd-w-list-empty">{{ listEmpty }}</div>
    </div>
    <ul v-else-if="kind === 'tree'" class="pd-w-tree">
      <li v-for="n in treeData" :key="n.title">
        {{ n.title }}
        <ul v-if="n.children?.length"><li v-for="c in n.children" :key="c.title">{{ c.title }}</li></ul>
      </li>
    </ul>

    <!-- 图表（SVG 骨架，预览数值驱动形态） -->
    <div v-else-if="isChart" class="pd-w-chart">
      <svg viewBox="0 0 100 60" preserveAspectRatio="none" class="pd-w-svg">
        <template v-if="seriesType === 'bar'">
          <rect v-for="(b, i) in barRects" :key="i" :x="b.x" :y="b.y" :width="b.w" :height="b.h" rx="1" :class="{ 'is-demo': b.demo }" />
        </template>
        <template v-else-if="seriesType === 'line'">
          <polyline :points="linePoints" fill="none" stroke-width="2" class="pd-w-stroke" />
        </template>
        <template v-else-if="seriesType === 'area'">
          <polygon :points="`0,${VB.h} ${linePoints} ${VB.w},${VB.h}`" class="pd-w-area" />
          <polyline :points="linePoints" fill="none" stroke-width="2" class="pd-w-stroke" />
        </template>
        <template v-else-if="seriesType === 'pie'">
          <g transform="translate(50,30)">
            <circle r="20" fill="none" stroke-width="16" class="pd-w-pie" />
            <circle
              v-for="s in pieSegs" :key="s.i" r="20" fill="none" stroke-width="16"
              :stroke-dasharray="s.dasharray" :stroke-dashoffset="s.offset" :class="{ 'is-demo': s.demo, [`pd-w-pie-${s.i % 4}`]: true }"
            />
          </g>
        </template>
        <template v-else-if="seriesType === 'gauge'">
          <g transform="translate(50,55)">
            <path d="M -30 0 A 30 30 0 0 1 30 0" fill="none" stroke-width="8" class="pd-w-gauge-bg" :stroke-dasharray="gaugeArc.bg" />
            <path d="M -30 0 A 30 30 0 0 1 30 0" fill="none" stroke-width="8" class="pd-w-gauge-fg" :stroke-dasharray="gaugeArc.fg" />
            <text y="-6" text-anchor="middle" class="pd-w-svg-text">{{ gaugePct }}%</text>
          </g>
        </template>
        <template v-else>
          <circle v-for="(p, i) in scatterPts" :key="i" :cx="p.x" :cy="p.y" r="3" :class="{ 'is-demo': p.demo }" />
        </template>
        <text v-if="!pvOk && seriesType !== 'gauge'" :x="50" :y="seriesType === 'pie' ? 58 : 34" text-anchor="middle" class="pd-w-svg-text">{{ chartEmpty }}</text>
      </svg>
    </div>

    <!-- 绑定元素 -->
    <span v-else-if="isBinding" class="pd-w-bind" :style="kind === 'sys-status' ? { color: bindColor, borderColor: bindColor } : undefined">
      <i class="pd-w-bind-dot" :style="{ background: kind === 'sys-status' ? bindColor : '#1677ff' }" />{{ bindVal }}
    </span>

    <span v-else class="pd-w-unknown">{{ widget.kind }}</span>

    <div v-if="!broken" class="pd-w-grip" title="拖拽调尺寸" @mousedown="startResize" />
  </div>
</template>

<style scoped>
.pd-w-root {
  position: absolute;
  box-sizing: border-box;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.4;
  color: #1f2329;
  cursor: default;
}
.pd-w-root.is-selected {
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.18);
}
.pd-w-root:hover {
  border-color: rgba(22, 119, 255, 0.45);
}
.pd-w-broken {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 4px;
  font-size: 12px;
  color: #f54a45;
  background: #fff2f0;
  border: 1px dashed #f54a45;
  border-radius: 6px;
}
.pd-w-grip {
  position: absolute;
  right: -4px;
  bottom: -4px;
  width: 10px;
  height: 10px;
  border-radius: 3px;
  background: #1677ff;
  opacity: 0;
  cursor: se-resize;
}
.pd-w-root:hover .pd-w-grip,
.pd-w-root.is-selected .pd-w-grip {
  opacity: 1;
}

/* 容器 */
.pd-w-kids {
  position: relative;
  flex: 1;
  min-height: 0;
}
.pd-w-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 8px;
  background: #ffffff;
  border: 1px solid #e5e6eb;
  border-radius: 12px;
}
.pd-w-card-title {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
}
.pd-w-grid {
  display: grid;
  gap: 8px;
  height: 100%;
}
.pd-w-tabs,
.pd-w-collapse {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.pd-w-tabs-head {
  display: flex;
  gap: 12px;
  padding-bottom: 4px;
  margin-bottom: 6px;
  border-bottom: 1px solid #e5e6eb;
}
.pd-w-tab {
  font-size: 12px;
  color: #86909c;
}
.pd-w-tab.is-active {
  color: #1677ff;
  border-bottom: 2px solid #1677ff;
}
.pd-w-collapse-item {
  margin-bottom: 6px;
  border: 1px solid #e5e6eb;
  border-radius: 8px;
}
.pd-w-collapse-title {
  padding: 4px 8px;
  font-size: 12px;
  background: #f7f8fa;
}

/* 基础元素 */
.pd-w-text {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pd-w-heading {
  font-weight: 600;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pd-w-link {
  color: #1677ff;
  text-decoration: underline;
}
.pd-w-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  color: #ffffff;
  font-size: 11px;
  line-height: 18px;
}
.pd-w-btn {
  padding: 4px 14px;
  color: #ffffff;
  background: #1677ff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  cursor: not-allowed;
  opacity: 0.85;
}
.pd-w-ico {
  color: #1677ff;
}
.pd-w-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 8px;
  background: #f2f3f5;
}
.pd-w-rich {
  overflow: hidden;
}
.pd-w-divider {
  height: 1px;
  width: 100%;
}
.pd-w-spacer {
  width: 100%;
}

/* 表单 */
.pd-w-field {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 100%;
}
.pd-w-field-label {
  flex: none;
  font-size: 12px;
  color: #4e5969;
}
.pd-w-input,
.pd-w-textarea {
  flex: 1;
  min-width: 0;
  height: 26px;
  padding: 2px 8px;
  color: #86909c;
  background: #ffffff;
  border: 1px solid #e5e6eb;
  border-radius: 6px;
  font-size: 12px;
  cursor: not-allowed;
}
.pd-w-textarea {
  height: 100%;
  resize: none;
}
.pd-w-select {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: space-between;
  height: 26px;
  padding: 0 8px;
  background: #ffffff;
  border: 1px solid #e5e6eb;
  border-radius: 6px;
  font-size: 12px;
  color: #86909c;
}
.pd-w-caret {
  color: #86909c;
  font-style: normal;
}
.pd-w-switch {
  position: relative;
  flex: none;
  width: 32px;
  height: 18px;
  border-radius: 9px;
  background: #c9cdd4;
  transition: background 0.2s;
}
.pd-w-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #ffffff;
}
.pd-w-switch.is-on {
  background: #1677ff;
}
.pd-w-switch.is-on::after {
  left: 16px;
}
.pd-w-slider {
  position: relative;
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background: #e5e6eb;
}
.pd-w-slider-fill {
  height: 100%;
  border-radius: 2px;
  background: #1677ff;
}
.pd-w-opts {
  display: inline-flex;
  gap: 10px;
  align-items: center;
  font-size: 12px;
}
.pd-w-opt {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}
.pd-w-upload {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 26px;
  font-size: 12px;
  color: #4e5969;
  background: #f7f8fa;
  border: 1px dashed #c9cdd4;
  border-radius: 6px;
}

/* table */
.pd-w-table {
  width: 100%;
  height: 100%;
  border-collapse: collapse;
  font-size: 12px;
  background: #ffffff;
}
.pd-w-table th,
.pd-w-table td {
  padding: 4px 8px;
  text-align: left;
  border-bottom: 1px solid #f2f3f5;
}
.pd-w-table th {
  color: #4e5969;
  font-weight: 600;
  background: #f7f8fa;
}
.pd-w-table-empty {
  color: #86909c;
  text-align: center;
}

/* 数据展示 */
.pd-w-stat-title {
  font-size: 12px;
  color: #86909c;
}
.pd-w-stat-value {
  font-size: 20px;
  font-weight: 600;
  color: #1d2129;
}
.pd-w-progress {
  width: 100%;
  height: 8px;
  border-radius: 4px;
  background: #e5e6eb;
  overflow: hidden;
}
.pd-w-progress-fill {
  height: 100%;
  border-radius: 4px;
  background: #1677ff;
  transition: width 0.2s;
}
.pd-w-desc-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
  padding: 2px 0;
  border-bottom: 1px dashed #f2f3f5;
}
.pd-w-desc-label {
  flex: none;
  width: 64px;
  color: #86909c;
}
.pd-w-desc-value {
  color: #1f2329;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pd-w-timeline {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  list-style: none;
}
.pd-w-timeline li {
  position: relative;
  padding-bottom: 8px;
}
.pd-w-timeline li::before {
  content: '';
  position: absolute;
  left: -12px;
  top: 5px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #1677ff;
}
.pd-w-list-item {
  padding: 3px 0;
  font-size: 12px;
  border-bottom: 1px solid #f2f3f5;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pd-w-list-empty {
  padding: 12px 0;
  font-size: 12px;
  color: #86909c;
  text-align: center;
}
.pd-w-tree {
  margin: 0;
  padding-left: 14px;
  font-size: 12px;
  list-style: none;
}
.pd-w-tree li {
  padding: 2px 0;
}

/* 图表 */
.pd-w-chart {
  width: 100%;
  height: 100%;
  background: #ffffff;
}
.pd-w-svg {
  width: 100%;
  height: 100%;
}
.pd-w-svg rect {
  fill: #1677ff;
}
.pd-w-svg rect.is-demo,
.pd-w-svg circle.is-demo {
  fill: #c9cdd4;
}
.pd-w-stroke {
  stroke: #1677ff;
}
.pd-w-area {
  fill: rgba(22, 119, 255, 0.18);
}
.pd-w-pie {
  stroke: #f2f3f5;
}
.pd-w-pie-0 {
  stroke: #1677ff;
}
.pd-w-pie-1 {
  stroke: #36cfc9;
}
.pd-w-pie-2 {
  stroke: #f7ba1e;
}
.pd-w-pie-3 {
  stroke: #722ed1;
}
.pd-w-gauge-bg {
  stroke: #e5e6eb;
}
.pd-w-gauge-fg {
  stroke: #1677ff;
}
.pd-w-svg-text {
  font-size: 9px;
  fill: #86909c;
}

/* 绑定元素 */
.pd-w-bind {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  max-width: 100%;
  padding: 1px 8px;
  font-size: 12px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  background: #f2f7ff;
  border: 1px solid rgba(22, 119, 255, 0.35);
  border-radius: 10px;
  color: #1677ff;
}
.pd-w-bind-dot {
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.pd-w-unknown {
  font-size: 12px;
  color: #86909c;
}
</style>

<script setup lang="ts">
/**
 * FieldLineageMap（Task 6 字段级图上呈现）：选中表的字段映射图。
 * 左列来源表字段 / 右列目标表字段 / 中间 field_dep 连线 + transform 悬浮标签（hover）。
 * 数据契约（GET /lineage/fields，datara-backend/api/lineage.py §6 唯一权威）：
 * target =「裸表.字段」、from =「裸表.字段」（常量项 from="" 已由视图层过滤）。
 * 表部/字段部按最后一个点分界（对齐后端 rpartition 口径），全程裸表名展示，
 * 不混入 fq/数据源信息（规避运行态采集侧 field 挂靠与表级 fq 的错位语义）。
 * 简单两列布局 + SVG 拉伸连线（字段数通常 <50，不上画布引擎）。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'

export interface FieldMapRow { target: string; from: string; transform: string }

const props = defineProps<{ rows: FieldMapRow[]; highlight?: string }>()

/** 行高（px）：左右列与连线 y 坐标统一按此对齐 */
const ROW_H = 34

/** "a.b.c" → 表部 "a.b" + 字段部 "c"（最后一段为字段名；无点整体视作字段名兜底） */
function splitField(name: string): { table: string; field: string } {
  const i = name.lastIndexOf('.')
  return i < 0 ? { table: '', field: name } : { table: name.slice(0, i), field: name.slice(i + 1) }
}

/** 左列：来源字段去重（同表相邻排序：表名字典序 → 字段名字典序） */
const lefts = computed(() => {
  const seen = new Map<string, { id: string; table: string; field: string }>()
  props.rows.forEach((r) => {
    if (r.from && !seen.has(r.from)) seen.set(r.from, { id: r.from, ...splitField(r.from) })
  })
  return [...seen.values()].sort((a, b) =>
    a.table === b.table ? a.field.localeCompare(b.field) : a.table.localeCompare(b.table))
})

/** 右列：目标字段去重（首次出现序） */
const rights = computed(() => {
  const seen = new Set<string>()
  props.rows.forEach((r) => seen.add(splitField(r.target).field))
  return [...seen]
})

/** 连线：映射行 → 左右索引；端点任一缺失（数据不自洽）的行不参与连线，
 * 避免索引兜底贴顶画错线（Task 6 审查 M-1） */
const edges = computed(() => {
  const li = new Map(lefts.value.map((n, i) => [n.id, i]))
  const ri = new Map(rights.value.map((f, i) => [f, i]))
  const out: { li: number; ri: number; transform: string }[] = []
  props.rows.forEach((r) => {
    const l = li.get(r.from)
    const rr = ri.get(splitField(r.target).field)
    if (l !== undefined && rr !== undefined) out.push({ li: l, ri: rr, transform: r.transform })
  })
  return out
})

const bodyH = computed(() => Math.max(lefts.value.length, rights.value.length, 1) * ROW_H)

const hoverIdx = ref(-1)
const activeField = ref('')
const rootEl = ref<HTMLElement | null>(null)

/** 深链 field 定位：仅滚动映射图容器自身，把命中 chip（.hl）滚到垂直居中。
 * 不用 scrollIntoView——block:'center' 会波及所有可滚祖先，页内嵌场景外层被滚走（Task 6 审查 M-3） */
watch(() => props.highlight, () => { void scrollHighlight() })
onMounted(() => { void scrollHighlight() })
async function scrollHighlight() {
  if (!props.highlight) return
  await nextTick()
  const box = rootEl.value
  const chip = box?.querySelector<HTMLElement>('.flm-chip.hl')
  if (!box || !chip) return
  const delta = chip.getBoundingClientRect().top - box.getBoundingClientRect().top
  box.scrollTop += delta - box.clientHeight / 2 + chip.offsetHeight / 2
}
</script>

<template>
  <div ref="rootEl" class="flm">
    <div class="flm-head">
      <span>来源字段（{{ lefts.length }}）</span>
      <span>目标字段（{{ rights.length }}）</span>
    </div>
    <div class="flm-body" :style="{ height: bodyH + 'px' }">
      <div class="flm-col flm-col-l">
        <div
          v-for="(n, i) in lefts" :key="n.id"
          class="flm-chip mono"
          :class="{ hl: highlight === n.id, on: activeField === n.id }"
          :style="{ top: i * ROW_H + 4 + 'px' }"
          @mouseenter="activeField = n.id" @mouseleave="activeField = ''"
        >
          <i v-if="n.table" class="flm-tbl">{{ n.table }}</i><span>{{ n.field }}</span>
        </div>
      </div>
      <svg class="flm-svg" :viewBox="`0 0 100 ${bodyH}`" preserveAspectRatio="none" aria-hidden="true">
        <g v-for="(e, i) in edges" :key="i" @mouseenter="hoverIdx = i" @mouseleave="hoverIdx = -1">
          <!-- 透明宽线扩大 hover 捕获区；可见线 vector-effect 防拉伸变形 -->
          <line class="flm-hit" x1="45" :y1="e.li * ROW_H + ROW_H / 2" x2="55" :y2="e.ri * ROW_H + ROW_H / 2" />
          <line
            class="flm-line"
            :class="{
              hl: highlight && (lefts[e.li]!.id === highlight || rights[e.ri] === highlight),
              on: activeField && (lefts[e.li]!.id === activeField || rights[e.ri] === activeField),
              dim: !!activeField && lefts[e.li]!.id !== activeField && rights[e.ri] !== activeField,
            }"
            x1="45" :y1="e.li * ROW_H + ROW_H / 2" x2="55" :y2="e.ri * ROW_H + ROW_H / 2"
          />
        </g>
      </svg>
      <div class="flm-col flm-col-r">
        <div
          v-for="(f, i) in rights" :key="f"
          class="flm-chip mono"
          :class="{ hl: highlight === f, on: activeField === f }"
          :style="{ top: i * ROW_H + 4 + 'px' }"
          @mouseenter="activeField = f" @mouseleave="activeField = ''"
        >{{ f }}</div>
      </div>
      <!-- transform 悬浮标签（连线 hover）；首行连线翻转垂直居中防顶部越界裁剪（Task 6 审查 M-4） -->
      <div
        v-if="hoverIdx >= 0" class="flm-tip mono"
        :class="{ flip: edges[hoverIdx]!.li + edges[hoverIdx]!.ri === 0 }"
        :style="{ top: ((edges[hoverIdx]!.li + edges[hoverIdx]!.ri) * ROW_H) / 2 + ROW_H / 2 + 'px' }"
      >{{ edges[hoverIdx]!.transform || '（无表达式）' }}</div>
    </div>
  </div>
</template>

<style scoped>
.flm{flex:1;min-height:0;overflow:auto;background:#fff;padding:10px 14px}
.flm-head{display:flex;justify-content:space-between;max-width:860px;margin:0 auto;font-size:11px;color:var(--text-3);padding:0 4px 6px}
.flm-body{position:relative;max-width:860px;margin:0 auto}
.flm-col{position:absolute;top:0;bottom:0;width:44%}
.flm-col-l{left:0}
.flm-col-r{right:0}
.flm-chip{position:absolute;left:0;right:0;height:26px;display:flex;align-items:center;gap:6px;padding:0 10px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);font-size:11.5px;white-space:nowrap;overflow:hidden;transition:border-color var(--dur-base) var(--ease),background var(--dur-base) var(--ease)}
.flm-col-l .flm-chip{justify-content:flex-end}
.flm-col-r .flm-chip{justify-content:flex-start}
.flm-tbl{font-style:normal;color:var(--text-3);font-size:10.5px;flex-shrink:0}
.flm-svg{position:absolute;inset:0;width:100%;height:100%}
.flm-hit{stroke:transparent;stroke-width:10;vector-effect:non-scaling-stroke}
.flm-line{stroke:#b6c2d4;stroke-width:1.5;vector-effect:non-scaling-stroke;pointer-events:none;transition:stroke var(--dur-base) var(--ease)}
.flm-line.on{stroke:var(--primary);stroke-width:2}
.flm-line.hl{stroke:#d97706;stroke-width:2}
.flm-line.dim{stroke-opacity:.25}
.flm-chip.on{border-color:var(--primary)}
.flm-chip.hl{border-color:#d97706;background:#fff7ed}
.flm-tip{position:absolute;left:50%;transform:translate(-50%,-130%);background:#1f2937;color:#fff;font-size:10.5px;padding:3px 8px;border-radius:4px;pointer-events:none;max-width:60%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;z-index:2}
.flm-tip.flip{transform:translate(-50%,-50%)}
</style>

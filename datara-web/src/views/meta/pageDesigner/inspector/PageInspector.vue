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
 *   手动输入确认/blur → resolveFallback(placeholder, input) 落 fallback（空值落 placeholder 文案）；
 *   dataset 槽回显 ds:{id} 时附库表钻取区（D3/M3）：库→表→字段懒加载（库列表按 dsId 组件内缓存），
 *   选表生成只读查询绑定 SELECT * FROM db.table（免手写 SQL，可直接预览）；换数据源保留已生成 query；
 *   钻取是辅助器，不改变绑定回显。
 * 布局/样式输入为受控合成 patch（以当前值合成完整对象，合并归宿主），无本地镜像状态。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CANVAS_H, CANVAS_W, type PageDSL, type Rect, type WidgetNode } from '../designerModel'
import { candidatesFor, resolveFallback, type ResourceCatalog, type SlotType } from '../bindingCatalog'
import { widgetTemplate } from '../templates'
import { pdColumns, pdDatabases, pdTables, type DsColumnMeta, type DsTableItem } from '../pageApi'

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

/* 下拉选择：kind 由候选来源映射（bindingOf）；清空（allowClear）→ 静态默认值；
   ds: 选择保留既有 query SQL（D3：换数据源不自动清除已生成绑定，显式重选表才覆盖） */
function onPick(s: SlotSpec, value: unknown) {
  const w = sel.value
  if (!w) return
  const fb = slotPlaceholder(w, s)
  const v = value == null || value === '' ? undefined : String(value)
  if (v?.startsWith('ds:')) {
    const prev = w.bindings[s.key]
    const query = prev?.kind === 'query' && prev.query ? prev.query : undefined
    const b = bindingOf(v, fb)
    emit('updateWidget', w.id, { bindings: { [s.key]: query ? { ...b, query } : b } })
    return
  }
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

/* ================= dataset 槽库表钻取（D3/M3）：库→表→字段，选表生成只读查询绑定 ================= */
const ddDbCache = new Map<number, string[]>() // dsId → 库列表（组件内缓存，避免重复请求）
const ddDbs = ref<string[]>([])
const ddDb = ref('')
const ddTables = ref<DsTableItem[]>([])
const ddTable = ref('')
const ddCols = ref<DsColumnMeta[]>([])
const ddLoadingDb = ref(false)
const ddLoadingTable = ref(false)
const ddLoadingCols = ref(false)

/** 钻取条件：dataset 槽且当前回显为 ds:{id}（辅助器不改变绑定回显） */
const ddDsId = computed<number | null>(() => {
  const s = slots.value.find((x) => x.slot === 'dataset')
  if (!s || !sel.value) return null
  const v = currentBindValue(s)
  if (!v.startsWith('ds:')) return null
  const id = Number(v.slice(3))
  return Number.isFinite(id) ? id : null
})

/* dsId 变化（含钻取区首次出现）→ 重置库/表/字段并懒拉库列表（命中缓存不重复请求） */
watch(ddDsId, (id) => {
  ddDb.value = ''
  ddTable.value = ''
  ddDbs.value = []
  ddTables.value = []
  ddCols.value = []
  if (id != null) void ensureDbs(id)
}, { immediate: true })

async function ensureDbs(id: number): Promise<void> {
  const hit = ddDbCache.get(id)
  if (hit) {
    ddDbs.value = hit
    return
  }
  ddLoadingDb.value = true
  try {
    const dbs = await pdDatabases(id)
    ddDbCache.set(id, dbs)
    ddDbs.value = dbs
  } catch (e) {
    ElMessage.error(`库列表加载失败：${e instanceof Error ? e.message : String(e)}`)
  } finally {
    ddLoadingDb.value = false
  }
}

/* 选库：懒拉表清单；已生成 query 绑定不自动清除（显式重选表才覆盖），仅重置表/字段选择器 */
async function onDdDb(db: unknown): Promise<void> {
  ddDb.value = db == null || db === '' ? '' : String(db)
  ddTable.value = ''
  ddTables.value = []
  ddCols.value = []
  const id = ddDsId.value
  if (ddDb.value === '' || id == null) return
  ddLoadingTable.value = true
  try {
    ddTables.value = await pdTables(id, ddDb.value)
  } catch (e) {
    ElMessage.error(`表清单加载失败：${e instanceof Error ? e.message : String(e)}`)
  } finally {
    ddLoadingTable.value = false
  }
}

/** 表选项摘要：name (kind · rows)，rows 缺省省略 */
const ddTableLabel = (t: DsTableItem): string => (t.rows != null ? `${t.name} (${t.kind} · ${t.rows})` : `${t.name} (${t.kind})`)

/* 选表：生成只读查询绑定（SELECT * FROM db.table，免手写 SQL 可直接预览）+ 懒拉字段展示 */
function onDdTable(name: unknown): void {
  const w = sel.value
  const s = slots.value.find((x) => x.slot === 'dataset')
  const id = ddDsId.value
  const t = name == null || name === '' ? '' : String(name)
  ddTable.value = t
  ddCols.value = []
  if (t === '' || id == null || !w || !s) return
  void loadCols(id, ddDb.value, t)
  emit('updateWidget', w.id, {
    bindings: {
      [s.key]: { kind: 'query', datasourceId: id, query: `SELECT * FROM ${ddDb.value}.${t}`, fallback: slotPlaceholder(w, s) },
    },
  })
}

async function loadCols(id: number, db: string, table: string): Promise<void> {
  ddLoadingCols.value = true
  try {
    ddCols.value = await pdColumns(id, db, table)
  } catch (e) {
    ElMessage.error(`字段加载失败：${e instanceof Error ? e.message : String(e)}`)
  } finally {
    ddLoadingCols.value = false
  }
}

/** 字段标签最多 12 个，溢出聚合 …N more */
const ddShownCols = computed(() => ddCols.value.slice(0, 12))
const ddMoreCols = computed(() => Math.max(0, ddCols.value.length - 12))

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
          <!-- 数据集槽库表钻取（D3/M3）：库→表→字段，选表生成只读查询绑定；辅助器不改变绑定回显 -->
          <div v-if="s.slot === 'dataset' && currentBindValue(s).startsWith('ds:')" class="pd-insp-dd">
            <label class="pd-insp-field"><span>库</span>
              <el-select
                class="pd-insp-dd-db" :model-value="ddDb" :loading="ddLoadingDb" clearable
                placeholder="选择库" @update:model-value="onDdDb"
              >
                <el-option v-for="d in ddDbs" :key="d" :label="d" :value="d" />
              </el-select>
            </label>
            <label class="pd-insp-field"><span>表</span>
              <el-select
                class="pd-insp-dd-tb" :model-value="ddTable" :loading="ddLoadingTable" :disabled="ddDb === ''" clearable
                placeholder="选择表" @update:model-value="onDdTable"
              >
                <el-option v-for="t in ddTables" :key="t.name" :label="ddTableLabel(t)" :value="t.name" />
              </el-select>
            </label>
            <div v-if="ddShownCols.length > 0" class="pd-insp-dd-cols">
              <el-tag v-for="c in ddShownCols" :key="c.name" size="small" class="pd-insp-dd-col">{{ c.name }}:{{ c.dataType }}</el-tag>
              <span v-if="ddMoreCols > 0" class="pd-insp-dd-more">…{{ ddMoreCols }} more</span>
            </div>
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
.pd-insp-dd {
  display: grid;
  gap: 6px;
  margin-top: 6px;
}
.pd-insp-dd :deep(.el-select) {
  flex: 1;
  min-width: 0;
}
.pd-insp-dd-cols {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.pd-insp-dd-more {
  font-size: 11px;
  color: var(--text-2);
}
</style>

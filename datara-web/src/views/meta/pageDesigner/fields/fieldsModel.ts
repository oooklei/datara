/**
 * fields 声明式组件编辑模型（组件设计器「表单定义模式」）。
 *
 * 背景：组件 spec 两类——page 组件（spec.page = 页面 DSL）与声明式组件。
 * 声明式落库有两种形态：
 * - M1 §10.1：spec.fields = SpecField[]（用户组件草稿/发布链）；
 * - 八段底稿（基线化认可发版）：spec.form.params = FormFieldDecl[]——内置组件
 *   6002 重开修订草稿复制的正是它。
 * 本模块把两种形态统一为「字段行」编辑模型：行对象浅拷贝保留未知键
 * （showIf/cap/visible 等不因编辑丢字段），保存时按来源键原位写回，其余
 * spec 内容（八段其余各段/ports/lineage…）深拷贝底板原样保留。
 *
 * 组件初始化：spec 无任何字段行时，从目录详情 formFields（导出脚本已把
 * 22 种旧控件收敛为 9 基元 type）物化初始表单——打开设计器即见该组件的
 * 参数表单，而非空白。
 * 纯数据、无副作用，可独立单测。
 */
import type { ComponentSpec } from '../../../../services/componentSpec'
import { ONCHANGE_ACTION_VALUES, PREFILL_FROM_VALUES, PICKER_VALUES, HIDDEN_INPUT_KEY_VALUES } from '../../../../services/componentSpec'
import { TYPE_COMPAT, type DataType } from '../../../../graph/model/portTypes'

/** outputs.type 合法域（DataType 枚举 = any/none + TYPE_COMPAT 键；与 normalizeSpec DATA_TYPE_SET 同派生口径） */
const DECL_DATA_TYPES = new Set<string>(['any', 'none', ...Object.keys(TYPE_COMPAT)])
const DECL_ONCHANGE_ACTIONS = new Set<string>(ONCHANGE_ACTION_VALUES)
const DECL_PREFILL_FROMS = new Set<string>(PREFILL_FROM_VALUES)
const DECL_PICKERS = new Set<string>(PICKER_VALUES)
const DECL_HIDDEN_INPUTS = new Set<string>(HIDDEN_INPUT_KEY_VALUES)

/** 字段行（已知键受控编辑 + 未知键原样保留；uiType 允许越界值透传显示，发布闸门兜底） */
export type FieldRow = Record<string, unknown> & {
  key: string
  label: string
  uiType: string
  required: boolean
}

/** 字段来源：M1 §10.1 spec.fields / 八段底稿 spec.form.params */
export type FieldsSource = 'fields' | 'form.params'

/** fields 模式编辑态 */
export interface FieldsState {
  source: FieldsSource
  rows: FieldRow[]
  dropPolicy: Record<string, unknown>
  /** Task 6：8 要素声明分片（身份/表现/outputs/扩展；undo 快照随 FieldsState 一并序列化） */
  decl: DeclState
  /** 原 spec 深拷贝底板（保存时仅替换来源键 + dropPolicy + decl，其余原样保留） */
  baseSpec: Record<string, unknown>
}

/** uiType 9 基元（与 componentSpec.SPEC_UI_TYPES 同口径；此处放宽为 string 白名单便于透传） */
export const FIELD_UI_TYPES = ['text', 'number', 'bool', 'select', 'expr', 'hint', 'rows', 'mapEditor', 'resource']

/* ── Task 6（方案§2.1/§2.6）：8 要素 4 组声明分片编辑态 ──
 * fields/dropPolicy 之外的可编辑声明（身份/表现/契约 outputs/扩展）统一进 decl 分片，
 * 与 rows/dropPolicy 同受 undo 快照与 toFieldsSpec 写回管理。
 * 类型严格取自 ComponentSpec（不双写结构定义），保证与 normalizeSpec/normBehaviors 枚举同源。 */

/** 声明式输出行（ComponentSpec.outputs 元素；type 为 DataType 枚举字符串） */
export type DeclOutput = NonNullable<ComponentSpec['outputs']>[number]
/** 状态徽标（ComponentSpec.badge） */
export type DeclBadge = NonNullable<ComponentSpec['badge']>
/** 声明式行为（ComponentSpec.behaviors；枚举值经编辑器下拉限定为合法值） */
export type DeclBehaviors = NonNullable<ComponentSpec['behaviors']>
/** 扩展能力（ComponentSpec.extensions；hiddenInputs 放宽为 string 便于透传显示） */
export interface DeclExtensions {
  hiddenInputs?: string[]
  capabilities?: { testable?: boolean; previewLimit?: number }
}

/** 8 要素 4 组声明分片（身份/表现/契约 outputs/扩展；fields 与 dropPolicy 走 FieldsState 原字段） */
export interface DeclState {
  /* 身份组（summary/icon/color 为 ComponentSpec 一级必有字段；type 只读展示由宿主传 draft.type） */
  summary: string
  displayName?: string
  aliases?: string[]
  description?: string
  category?: string
  docUrl?: string
  /* 表现组 */
  icon: string
  color: string
  badge?: DeclBadge
  behaviors?: DeclBehaviors
  /* 契约组 outputs（fields 在 FieldsState.rows） */
  outputs?: DeclOutput[]
  /* 扩展组（dropPolicy 在 FieldsState.dropPolicy） */
  extensions?: DeclExtensions
  initTemplate?: Record<string, unknown>
  specVersion?: string
}

/** 宽松提取字符串（非字符串缺位，对齐 normOptString） */
function optStr(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined
}

/** spec → decl 分片编辑态（宽进：宽松 JSON 逐键提取，非法形状缺位，编辑器内再收敛） */
export function loadDeclState(s: Record<string, unknown>): DeclState {
  const d: DeclState = {
    summary: String(s.summary ?? ''),
    icon: String(s.icon ?? ''),
    color: String(s.color ?? ''),
  }
  const displayName = optStr(s.displayName)
  if (displayName !== undefined) d.displayName = displayName
  if (Array.isArray(s.aliases)) d.aliases = s.aliases.filter((x): x is string => typeof x === 'string')
  const description = optStr(s.description)
  if (description !== undefined) d.description = description
  const category = optStr(s.category)
  if (category !== undefined) d.category = category
  const docUrl = optStr(s.docUrl)
  if (docUrl !== undefined) d.docUrl = docUrl
  if (Array.isArray(s.outputs)) {
    const outs = s.outputs.flatMap((x): DeclOutput[] => {
      if (x === null || typeof x !== 'object' || Array.isArray(x)) return []
      const o = x as Record<string, unknown>
      /* 白名单收敛：type 非法（脏值）整行丢弃，不透传保存（与 normBehaviors 非法枚举丢弃先例同口径） */
      const t = String(o.type ?? '')
      if (!DECL_DATA_TYPES.has(t)) return []
      const item: DeclOutput = { name: String(o.name ?? ''), type: t as DataType }
      const desc = optStr(o.desc)
      if (desc !== undefined) item.desc = desc
      return [item]
    })
    /* 全部被收敛丢弃 → 不落键（与 behaviors 空判定一致，避免 outputs:[] 落 JSON） */
    if (outs.length > 0) d.outputs = outs
  }
  if (s.badge !== null && typeof s.badge === 'object' && !Array.isArray(s.badge)) {
    const b = s.badge as Record<string, unknown>
    if (typeof b.key === 'string' && b.colorMap !== null && typeof b.colorMap === 'object' && !Array.isArray(b.colorMap)) {
      const colorMap: Record<string, string> = {}
      for (const [k, v] of Object.entries(b.colorMap as Record<string, unknown>)) {
        if (typeof v === 'string') colorMap[k] = v
      }
      d.badge = { key: b.key, colorMap }
    }
  }
  if (s.behaviors !== null && typeof s.behaviors === 'object' && !Array.isArray(s.behaviors)) {
    const raw = s.behaviors as Record<string, unknown>
    const bh: DeclBehaviors = {}
    if (Array.isArray(raw.onChange)) {
      bh.onChange = raw.onChange.flatMap((x): NonNullable<DeclBehaviors['onChange']> => {
        if (x === null || typeof x !== 'object' || Array.isArray(x)) return []
        const o = x as Record<string, unknown>
        /* 白名单收敛：action 非法整行丢弃（与 normalizeSpec.normBehaviors 同口径，脏值不透传保存） */
        if (typeof o.field !== 'string' || typeof o.action !== 'string' || !DECL_ONCHANGE_ACTIONS.has(o.action)) return []
        const item: NonNullable<DeclBehaviors['onChange']>[number] = { field: o.field, action: o.action as 'refreshOptions' }
        if (Array.isArray(o.target)) item.target = o.target.filter((t): t is string => typeof t === 'string')
        const remote = optStr(o.remote)
        if (remote !== undefined) item.remote = remote
        return [item]
      })
    }
    if (Array.isArray(raw.prefillFromUpstream)) {
      bh.prefillFromUpstream = raw.prefillFromUpstream.flatMap((x): NonNullable<DeclBehaviors['prefillFromUpstream']> => {
        if (x === null || typeof x !== 'object' || Array.isArray(x)) return []
        const o = x as Record<string, unknown>
        if (typeof o.field !== 'string' || typeof o.from !== 'string' || !DECL_PREFILL_FROMS.has(o.from)) return []
        return [{ field: o.field, from: o.from as 'input.table' }]
      })
    }
    if (Array.isArray(raw.pick)) {
      bh.pick = raw.pick.flatMap((x): NonNullable<DeclBehaviors['pick']> => {
        if (x === null || typeof x !== 'object' || Array.isArray(x)) return []
        const o = x as Record<string, unknown>
        if (typeof o.field !== 'string' || typeof o.picker !== 'string' || !DECL_PICKERS.has(o.picker)) return []
        return [{ field: o.field, picker: o.picker as 'table' }]
      })
    }
    if (Object.keys(bh).length > 0) d.behaviors = bh
  }
  if (s.extensions !== null && typeof s.extensions === 'object' && !Array.isArray(s.extensions)) {
    const raw = s.extensions as Record<string, unknown>
    const ext: DeclExtensions = {}
    if (Array.isArray(raw.hiddenInputs)) ext.hiddenInputs = raw.hiddenInputs.filter((x): x is string => typeof x === 'string' && DECL_HIDDEN_INPUTS.has(x))
    if (raw.capabilities !== null && typeof raw.capabilities === 'object' && !Array.isArray(raw.capabilities)) {
      const c = raw.capabilities as Record<string, unknown>
      const caps: NonNullable<DeclExtensions['capabilities']> = {}
      if (typeof c.testable === 'boolean') caps.testable = c.testable
      const limit = Number(c.previewLimit)
      if (Number.isFinite(limit) && limit > 0) caps.previewLimit = Math.min(Math.floor(limit), 100)
      if (Object.keys(caps).length > 0) ext.capabilities = caps
    }
    if (Object.keys(ext).length > 0) d.extensions = ext
  }
  if (s.initTemplate !== null && typeof s.initTemplate === 'object' && !Array.isArray(s.initTemplate)) {
    d.initTemplate = JSON.parse(JSON.stringify(s.initTemplate)) as Record<string, unknown>
  }
  const specVersion = optStr(s.specVersion)
  if (specVersion !== undefined) d.specVersion = specVersion
  return d
}

/** decl 分片写回 spec 底板：summary/icon/color 必有键始终写；V2 optional 键 undefined 即删除（缺位键不落 JSON，与 normalizeSpec 向后兼容契约一致） */
export function applyDeclSpec(out: Record<string, unknown>, d: DeclState): void {
  out.summary = d.summary
  out.icon = d.icon
  out.color = d.color
  const v2Keys = ['displayName', 'aliases', 'description', 'category', 'docUrl', 'outputs', 'badge', 'behaviors', 'extensions', 'initTemplate', 'specVersion'] as const
  for (const k of v2Keys) {
    const v = d[k]
    if (v === undefined) delete out[k]
    else out[k] = JSON.parse(JSON.stringify(v))
  }
}

function isObj(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

/** 字段所在位置：spec.fields 优先，其次八段底稿 form.params（含 params 为空的八段），兜底 fields */
export function detectFieldsSource(spec: unknown): FieldsSource {
  const s = isObj(spec) ? spec : {}
  if (Array.isArray(s.fields)) return 'fields'
  if (isObj(s.form)) return 'form.params'
  return 'fields'
}

/**
 * spec 判型：true = page 模式（页面 DSL 编辑），false = fields 模式（表单定义）。
 * spec.page 键存在 → page；声明式结构（fields/form）存在 → fields；
 * 两者皆无时按 executionModel=page 兜底判 page（其余一律 fields 空声明）。
 */
export function detectPageMode(spec: unknown, executionModel: string): boolean {
  const s = isObj(spec) ? spec : {}
  if ('page' in s) return true
  if (Array.isArray(s.fields) || isObj(s.form)) return false
  return executionModel === 'page'
}

/** 单行规范化：已知键归一化，未知键浅拷贝保留 */
export function normFieldRow(v: unknown): FieldRow {
  const o = isObj(v) ? v : {}
  return {
    ...o,
    key: String(o.key ?? ''),
    label: String(o.label ?? ''),
    uiType: String(o.uiType ?? ''),
    required: o.required === true,
  }
}

export function normFieldRows(v: unknown): FieldRow[] {
  return Array.isArray(v) ? v.map(normFieldRow) : []
}

/** 目录 formFields → 字段行（组件初始化；type 已是 9 基元，越界兜底 text） */
export function rowsFromCatalogFormFields(list: unknown): FieldRow[] {
  if (!Array.isArray(list)) return []
  const out: FieldRow[] = []
  for (const v of list) {
    const o = isObj(v) ? v : {}
    const t = String(o.type ?? '')
    const row: FieldRow = {
      key: String(o.key ?? ''),
      label: String(o.label ?? ''),
      uiType: FIELD_UI_TYPES.includes(t) ? t : 'text',
      required: o.required === true,
    }
    if (o.defaultValue !== undefined) row.default = o.defaultValue
    if (typeof o.placeholder === 'string' && o.placeholder) row.desc = o.placeholder
    if (Array.isArray(o.options) && o.options.length) {
      row.options = o.options.map((x) => {
        const r = isObj(x) ? x : {}
        const val = r.value
        return {
          label: String(r.label ?? ''),
          value: typeof val === 'string' || typeof val === 'number' ? val : String(val ?? ''),
        }
      })
    }
    if (row.key || row.label) out.push(row)
  }
  return out
}

/** dropPolicy 编辑态（已知键归一化，未知键保留；maxInstances 0 = 不限） */
export function normDropPolicy(v: unknown): Record<string, unknown> {
  const o = isObj(v) ? v : {}
  const ac = isObj(o.autoConnect) ? o.autoConnect : {}
  const mi = Number(o.maxInstances)
  return {
    ...o,
    snapToGrid: o.snapToGrid === true,
    autoName: String(o.autoName ?? ''),
    prefillFromUpstream: Array.isArray(o.prefillFromUpstream) ? o.prefillFromUpstream.map(String) : [],
    autoConnect: {
      ...ac,
      upstream: ac.upstream === 'none' ? 'none' : 'nearest',
      downstream: ac.downstream === 'none' ? 'none' : 'nearest',
    },
    maxInstances: Number.isFinite(mi) && mi > 0 ? Math.floor(mi) : 0,
  }
}

/** 服务端 spec → 编辑态（空声明 {} 也能得到可编辑骨架；JSON 克隆规避 Proxy 不可克隆） */
export function loadFieldsState(spec: unknown): FieldsState {
  const s = isObj(spec) ? spec : {}
  const source = detectFieldsSource(s)
  const rawRows = source === 'fields' ? s.fields : isObj(s.form) ? s.form.params : undefined
  return {
    source,
    rows: normFieldRows(rawRows),
    dropPolicy: normDropPolicy(s.dropPolicy),
    decl: loadDeclState(s),
    baseSpec: isObj(spec) ? (JSON.parse(JSON.stringify(spec)) as Record<string, unknown>) : {},
  }
}

/** 目录 formFields 物化初始表单（仅当前无字段行时生效——组件初始化语义） */
export function initWithCatalogRows(st: FieldsState, rows: FieldRow[]): FieldsState {
  if (st.rows.length > 0 || rows.length === 0) return st
  return { ...st, rows }
}

/**
 * 编辑态 → 保存 spec：baseSpec 深拷贝，来源键与 dropPolicy 原位写回，其余原样保留。
 * 用 JSON 克隆而非 structuredClone：编辑态（fieldsState）是 Vue 响应式 Proxy，
 * structuredClone 无法克隆 Proxy（DataCloneError），spec 本身是纯 JSON 数据。
 */
export function toFieldsSpec(st: FieldsState): Record<string, unknown> {
  const out = JSON.parse(JSON.stringify(st.baseSpec)) as Record<string, unknown>
  const rows = JSON.parse(JSON.stringify(st.rows)) as FieldRow[]
  if (st.source === 'fields') {
    out.fields = rows
  } else {
    const form = isObj(out.form) ? out.form : {}
    form.params = rows
    out.form = form
  }
  out.dropPolicy = JSON.parse(JSON.stringify(st.dropPolicy)) as Record<string, unknown>
  /* Task 6：8 要素声明分片原位写回（summary/icon/color 必有键；V2 optional 缺位删键） */
  applyDeclSpec(out, JSON.parse(JSON.stringify(st.decl)) as DeclState)
  return out
}

/** 新增字段行默认形态（八段来源补 visible，与 FormFieldDecl 语义对齐） */
export function makeFieldRow(source: FieldsSource): FieldRow {
  const row: FieldRow = { key: '', label: '', uiType: 'text', required: false }
  if (source === 'form.params') row.visible = true
  return row
}

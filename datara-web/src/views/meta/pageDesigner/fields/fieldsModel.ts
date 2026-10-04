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
  /** 原 spec 深拷贝底板（保存时仅替换来源键 + dropPolicy，其余原样保留） */
  baseSpec: Record<string, unknown>
}

/** uiType 9 基元（与 componentSpec.SPEC_UI_TYPES 同口径；此处放宽为 string 白名单便于透传） */
export const FIELD_UI_TYPES = ['text', 'number', 'bool', 'select', 'expr', 'hint', 'rows', 'mapEditor', 'resource']

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
  return out
}

/** 新增字段行默认形态（八段来源补 visible，与 FormFieldDecl 语义对齐） */
export function makeFieldRow(source: FieldsSource): FieldRow {
  const row: FieldRow = { key: '', label: '', uiType: 'text', required: false }
  if (source === 'form.params') row.visible = true
  return row
}

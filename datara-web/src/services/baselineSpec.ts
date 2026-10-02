/**
 * M-B0 组件基线化：八段 DSL 声明类型 + 归一化 + 结构校验（纯函数、无副作用、可单测）。
 *
 * 八段 DSL 是旧 NodeSchema.form（FieldSchema[]，见 graph/profiles/types.ts）的
 * 可序列化重建：旧声明携带 showIf/onChange/text 等不可序列化函数，目录导出后只剩
 * 布尔标记（componentApi.FormFieldFlags），基线化改用声明式条件（conditions.show）
 * 替代 showIf 函数；字段定义拆为 inputs/outputs/params 三段，横切关注点
 * （条件/约束/排除/引用变量/输出变量）独立成段。
 *
 * 校验复用 componentSpec.ts 的禁用片段全扫描思想（validateSpecPureData 递归扫描
 * FORBIDDEN_SNIPPETS + NaN/Infinity + autoName 占位符）+ 八段结构校验
 * （键白名单 / 字段必填 / uiType 9 基元 / 同段 key 唯一 / 引用完整性 / 枚举域）。
 * 归一化与 componentSpec.normalizeSpec 同风格：冻结空底稿 {} 也能得到完整可编辑形态。
 */
import { SPEC_UI_TYPES, validateSpecPureData, type SpecPort, type SpecUiType, type SpecViolation } from './componentSpec'

/** uiType 白名单集合（9 基元；与 componentSpec.SPEC_UI_TYPES 同源） */
const UI_TYPE_SET = new Set<string>(SPEC_UI_TYPES.map((t) => t.value))

/** 条件操作符白名单（conditions.when.op；声明式替代旧 showIf 函数；notEq/notIn 为 M-B2 file 组件 conditions 声明所用） */
export const SPEC_OPS = ['eq', 'ne', 'notEq', 'in', 'notIn', 'notEmpty', 'empty', 'gt', 'lt'] as const
export type SpecOp = (typeof SPEC_OPS)[number]
const OP_SET = new Set<string>(SPEC_OPS)

/** 引用变量域白名单（refs.scopes 五域：工作流/全局/环境/时间参数/上游输出） */
export const REF_SCOPES = ['wf', 'global', 'env', 'time', 'upstream'] as const
export type RefScope = (typeof REF_SCOPES)[number]
const SCOPE_SET = new Set<string>(REF_SCOPES)

/** 输出变量来源枚举（exports.from：结果集/日志行/输出端口负载） */
export const EXPORT_FROMS = ['result', 'log', 'output'] as const
export type ExportFrom = (typeof EXPORT_FROMS)[number]
const EXPORT_FROM_SET = new Set<string>(EXPORT_FROMS)

/** 约束类型白名单（constraints.type） */
export const CONSTRAINT_TYPES = ['min', 'max', 'regex', 'enum', 'requiredIf', 'notEmptyIf'] as const
export type ConstraintType = (typeof CONSTRAINT_TYPES)[number]
const CONSTRAINT_SET = new Set<string>(CONSTRAINT_TYPES)

/** 血缘资产类型白名单（lineage.assets[].assetType） */
export const LINEAGE_ASSET_TYPES = ['table', 'file', 'stream'] as const
export type LineageAssetType = (typeof LINEAGE_ASSET_TYPES)[number]
const ASSET_TYPE_SET = new Set<string>(LINEAGE_ASSET_TYPES)
const ASSET_ROLE_SET = new Set<string>(['source', 'target'])

/** 八段键白名单（form 对象仅允许这些键；越界键在 validateBaselineSpec 报违规） */
export const FORM_SECTION_KEYS = [
  'inputs', 'outputs', 'params', 'conditions', 'constraints', 'exclusions', 'refs', 'exports',
] as const
export type FormSectionKey = (typeof FORM_SECTION_KEYS)[number]
/** 三段字段段（conditions/constraints/refs 引用完整性的判定基准） */
export const FIELD_SECTIONS = ['inputs', 'outputs', 'params'] as const
export type FieldSectionKey = (typeof FIELD_SECTIONS)[number]

/* ================= 八段声明类型 ================= */

/** 三段表单字段声明（inputs/outputs/params 共用结构；纯数据，禁函数） */
export interface FormFieldDecl {
  key: string
  label: string
  /** 控件类型 = B3 收敛 9 基元（复用 componentSpec.SPEC_UI_TYPES 白名单） */
  uiType: SpecUiType
  required: boolean
  /** 设计态抽屉可见（false = 高级/隐藏字段，配置抽屉预览不渲染） */
  visible: boolean
  /** 默认值（编辑器文本输入；非字符串存量值原样保留，编辑后才变为字符串） */
  default?: unknown
  /** 提示文案（渲染为控件下方说明） */
  hint?: string
  /** select 静态候选（仅 uiType=select 携带，同 componentSpec.normField 条件展开） */
  options?: { label: string; value: string | number }[]
  /** resource 选择器差异参数（仅 uiType=resource 携带；对齐 graph/profiles/types.ts ResourcePick 的纯数据子集） */
  cap?: Record<string, unknown>
  /** text 多行（multiline=true → textarea） */
  multiline?: boolean
  /** textarea 行数（缺省 4） */
  rows?: number
  /** 脚本库互通语言标记（'txt'=内联脚本内容；存在 ⇒ 渲染脚本库控件） */
  language?: string
  placeholder?: string
  /** 表单分组标题（相邻同组字段归组渲染） */
  group?: string
}

/** 条件可见声明（conditions；替代旧不可序列化的 showIf 函数——when 满足时 show 列表字段才显示） */
export interface ConditionDecl {
  id: string
  when: { field: string; op: SpecOp; value?: unknown }
  /** 条件满足时显示的字段 key 列表（引用完整性：必须存在于三段字段键全集） */
  show: string[]
}

/** 字段级约束声明（constraints；type 白名单六种，msg 为违规提示文案） */
export interface ConstraintDecl {
  field: string
  type: ConstraintType
  value?: unknown
  msg?: string
}

/** 互斥排除声明（exclusions；when.field=value 时 exclude.field 禁选 values） */
export interface ExclusionDecl {
  when: { field: string; value?: unknown }
  exclude: { field: string; values: unknown[] }
}

/** 引用变量域白名单声明（refs；字段允许引用的变量域五选多） */
export interface RefDecl {
  field: string
  scopes: RefScope[]
}

/** 输出变量声明（exports；from=log 必须 logKey 指明日志行键名） */
export interface ExportVarDecl {
  key: string
  from: ExportFrom
  type: string
  desc?: string
  /** from='log' 必填：日志行中的键名 */
  logKey?: string
}

/** 血缘资产声明（lineage.assets；role=source/target，pick 为资产拾取声明） */
export interface LineageAssetDecl {
  role: 'source' | 'target'
  /** 资产拾取声明（引用三段字段 key 或字面量，如 'table'） */
  pick: string
  assetType: LineageAssetType
}

/** 八段表单（三段字段 + 五类横切声明） */
export interface EightSectionForm {
  inputs: FormFieldDecl[]
  outputs: FormFieldDecl[]
  params: FormFieldDecl[]
  conditions: ConditionDecl[]
  constraints: ConstraintDecl[]
  exclusions: ExclusionDecl[]
  refs: RefDecl[]
  exports: ExportVarDecl[]
}

/** 实测记录草稿（M-B0 证据区；后端契约暂无独立写入端点，暂存 spec.meta.testDrafts 随底稿保存） */
export interface TestRecordDraft {
  batch: string
  dataflow: string
  result: string
  note?: string
}

/** 迁移/备注元信息（可缺省；testDrafts 为实测记录暂存位） */
export interface BaselineSpecMeta {
  /** 旧声明迁移时间（diff/审计展示） */
  migratedAt?: string
  /** 迁移来源（如 'dag_catalog'） */
  source?: string
  note?: string
  /** 实测记录草稿（随底稿保存；后端 testRecords 独立端点就位后迁移） */
  testDrafts?: TestRecordDraft[]
}

/** 副标题分型规则（when=null 为兜底模板；template 支持 ${key} 插值，对齐 formLinkage.renderSummary） */
export interface BaselineSummaryRule {
  when: { field: string; op: SpecOp; value?: unknown } | null
  template: string
}

/** 基线化声明（spec 级内容；type/status/状态流转在 progress/draft 主数据，不随 spec 保存） */
export interface BaselineSpec {
  form: EightSectionForm
  lineage: { assets: LineageAssetDecl[] }
  /** 外观渲染（icon/color/summary/ports 对齐 componentSpec.ComponentSpec 的对应位） */
  render: {
    icon: string
    color: string
    /** 节点渲染形态（'card'/'device'，缺省 card） */
    shape?: string
    summary: string
    /** 副标题分型规则（声明序首条命中生效；缺省回退 summary 常量） */
    summaryRules?: BaselineSummaryRule[]
    ports: { inputs: SpecPort[]; outputs: SpecPort[] }
  }
  /** 拖入策略（纯数据；结构宽松透传，禁用片段由全扫描兜底） */
  dropPolicy: Record<string, unknown>
  /** 设计态面板可见（D1 闸门 §13-5：runtime-only 组件必须显式 false） */
  paletteVisible: boolean
  meta?: BaselineSpecMeta
}

/* ================= 归一化（normalizeBaselineSpec） ================= */

function asObj(v: unknown): Record<string, unknown> {
  return (v !== null && typeof v === 'object' && !Array.isArray(v) ? v : {}) as Record<string, unknown>
}
function asArr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : []
}

function normPort(v: unknown): SpecPort {
  const o = asObj(v)
  return { name: String(o.name ?? ''), type: String(o.type ?? '') }
}

function normOptions(v: unknown): { label: string; value: string | number }[] {
  return asArr(v).map((x) => {
    const r = asObj(x)
    const val = r.value
    return {
      label: String(r.label ?? ''),
      value: typeof val === 'string' || typeof val === 'number' ? val : String(val ?? ''),
    }
  })
}

function normFieldDecl(v: unknown): FormFieldDecl {
  const o = asObj(v)
  const rawUi = String(o.uiType ?? '')
  const uiType = (UI_TYPE_SET.has(rawUi) ? rawUi : 'text') as SpecUiType
  const out: FormFieldDecl = {
    key: String(o.key ?? ''),
    label: String(o.label ?? ''),
    uiType,
    required: o.required === true,
    visible: o.visible === false ? false : true,
  }
  if (o.default !== undefined) out.default = o.default
  if (typeof o.hint === 'string' && o.hint) out.hint = o.hint
  // options 仅 select 携带、cap 仅 resource 携带（对齐 normalizeSpec 的条件展开，保持 JSON 紧凑）
  if (uiType === 'select') out.options = normOptions(o.options)
  if (uiType === 'resource' && o.cap !== null && typeof o.cap === 'object' && !Array.isArray(o.cap)) {
    out.cap = o.cap as Record<string, unknown>
  }
  if (o.multiline === true) out.multiline = true
  if (o.rows !== undefined) {
    const n = Number(o.rows)
    if (Number.isFinite(n) && n > 0) out.rows = Math.floor(n)
  }
  if (typeof o.language === 'string' && o.language) out.language = o.language
  if (typeof o.placeholder === 'string' && o.placeholder) out.placeholder = o.placeholder
  if (typeof o.group === 'string' && o.group) out.group = o.group
  return out
}

function normCondition(v: unknown): ConditionDecl {
  const o = asObj(v)
  const when = asObj(o.when)
  const op = String(when.op ?? '')
  return {
    id: String(o.id ?? ''),
    when: {
      field: String(when.field ?? ''),
      op: (OP_SET.has(op) ? op : 'eq') as SpecOp,
      ...(when.value !== undefined ? { value: when.value } : {}),
    },
    show: asArr(o.show).map(String),
  }
}

function normConstraint(v: unknown): ConstraintDecl {
  const o = asObj(v)
  const t = String(o.type ?? '')
  return {
    field: String(o.field ?? ''),
    type: (CONSTRAINT_SET.has(t) ? t : 'min') as ConstraintType,
    ...(o.value !== undefined ? { value: o.value } : {}),
    ...(typeof o.msg === 'string' && o.msg ? { msg: o.msg } : {}),
  }
}

function normExclusion(v: unknown): ExclusionDecl {
  const o = asObj(v)
  const when = asObj(o.when)
  const ex = asObj(o.exclude)
  return {
    when: { field: String(when.field ?? ''), ...(when.value !== undefined ? { value: when.value } : {}) },
    exclude: { field: String(ex.field ?? ''), values: asArr(ex.values) },
  }
}

function normRef(v: unknown): RefDecl {
  const o = asObj(v)
  const scopes = asArr(o.scopes).map(String).filter((s) => SCOPE_SET.has(s)) as RefScope[]
  return { field: String(o.field ?? ''), scopes }
}

function normExport(v: unknown): ExportVarDecl {
  const o = asObj(v)
  const from = String(o.from ?? '')
  return {
    key: String(o.key ?? ''),
    from: (EXPORT_FROM_SET.has(from) ? from : 'result') as ExportFrom,
    type: String(o.type ?? ''),
    ...(typeof o.desc === 'string' && o.desc ? { desc: o.desc } : {}),
    ...(typeof o.logKey === 'string' && o.logKey ? { logKey: o.logKey } : {}),
  }
}

function normAsset(v: unknown): LineageAssetDecl {
  const o = asObj(v)
  const role = String(o.role ?? '')
  const at = String(o.assetType ?? '')
  return {
    role: (ASSET_ROLE_SET.has(role) ? role : 'source') as LineageAssetDecl['role'],
    pick: String(o.pick ?? ''),
    assetType: (ASSET_TYPE_SET.has(at) ? at : 'table') as LineageAssetType,
  }
}

function normTestDraft(v: unknown): TestRecordDraft {
  const o = asObj(v)
  return {
    batch: String(o.batch ?? ''),
    dataflow: String(o.dataflow ?? ''),
    result: String(o.result ?? ''),
    ...(typeof o.note === 'string' && o.note ? { note: o.note } : {}),
  }
}

function normSummaryRule(v: unknown): BaselineSummaryRule {
  const o = asObj(v)
  if (o.when === null || o.when === undefined) return { when: null, template: String(o.template ?? '') }
  const w = asObj(o.when)
  const op = String(w.op ?? '')
  return {
    when: {
      field: String(w.field ?? ''),
      op: (OP_SET.has(op) ? op : 'eq') as SpecOp,
      ...(w.value !== undefined ? { value: w.value } : {}),
    },
    template: String(o.template ?? ''),
  }
}

/** 服务端 spec → 编辑器规范化骨架（冻结空底稿 {} 也能得到完整可编辑形态） */
export function normalizeBaselineSpec(raw: unknown): BaselineSpec {
  const s = asObj(raw)
  const form = asObj(s.form)
  const lineage = asObj(s.lineage)
  const render = asObj(s.render)
  const ports = asObj(render.ports)
  const meta = asObj(s.meta)
  const out: BaselineSpec = {
    form: {
      inputs: asArr(form.inputs).map(normFieldDecl),
      outputs: asArr(form.outputs).map(normFieldDecl),
      params: asArr(form.params).map(normFieldDecl),
      conditions: asArr(form.conditions).map(normCondition),
      constraints: asArr(form.constraints).map(normConstraint),
      exclusions: asArr(form.exclusions).map(normExclusion),
      refs: asArr(form.refs).map(normRef),
      exports: asArr(form.exports).map(normExport),
    },
    lineage: { assets: asArr(lineage.assets).map(normAsset) },
    render: {
      icon: String(render.icon ?? ''),
      color: String(render.color ?? ''),
      ...(typeof render.shape === 'string' && render.shape ? { shape: render.shape } : {}),
      summary: String(render.summary ?? ''),
      ...(Array.isArray(render.summaryRules) && render.summaryRules.length
        ? { summaryRules: (render.summaryRules as unknown[]).map(normSummaryRule) }
        : {}),
      ports: {
        inputs: asArr(ports.inputs).map(normPort),
        outputs: asArr(ports.outputs).map(normPort),
      },
    },
    dropPolicy: asObj(s.dropPolicy),
    paletteVisible: s.paletteVisible === false ? false : true,
  }
  // meta 仅在有内容时落键（迁移标记/实测草稿可整体缺省）
  const metaOut: BaselineSpecMeta = {}
  if (typeof meta.migratedAt === 'string' && meta.migratedAt) metaOut.migratedAt = meta.migratedAt
  if (typeof meta.source === 'string' && meta.source) metaOut.source = meta.source
  if (typeof meta.note === 'string' && meta.note) metaOut.note = meta.note
  if (Array.isArray(meta.testDrafts)) metaOut.testDrafts = meta.testDrafts.map(normTestDraft)
  if (Object.keys(metaOut).length) out.meta = metaOut
  return out
}

/* ================= 校验（validateBaselineSpec） ================= */

/** 三段字段键全集（inputs+outputs+params；引用完整性判定基准） */
export function allFieldKeys(spec: BaselineSpec): string[] {
  return [...spec.form.inputs, ...spec.form.outputs, ...spec.form.params].map((f) => f.key)
}

function pushRefViolation(out: SpecViolation[], path: string, kind: string, key: string): void {
  out.push({ path, msg: `${path} 引用的字段「${key}」不存在于 inputs/outputs/params（${kind}）` })
}

/**
 * 八段声明结构校验（打字即校验真源）：
 * 1) 复用纯数据全扫描（禁用片段 + NaN/Infinity + autoName 占位符，红线 2 前端镜像）；
 * 2) form 八段键白名单；3) 三段字段 key/label/uiType 必填 + uiType∈9 基元 + 同段 key 唯一；
 * 4) conditions/constraints/exclusions/refs 引用的 key 必须存在于三段字段键全集；
 * 5) exports.from 枚举 + from=log 必有 logKey；6) lineage.role/pick/assetType 合法。
 * 返回违规清单（空数组 = 通过）。
 */
export function validateBaselineSpec(spec: unknown): SpecViolation[] {
  if (spec === null || typeof spec !== 'object' || Array.isArray(spec)) {
    return [{ path: '', msg: '声明必须是 JSON 对象' }]
  }
  const out: SpecViolation[] = []
  // 1) 纯数据全扫描（禁用片段/非严格 JSON 数值——八段与横切段一并覆盖）
  out.push(...validateSpecPureData(spec))
  const s = spec as Record<string, unknown>
  const form = s.form
  if (form === null || typeof form !== 'object' || Array.isArray(form)) {
    out.push({ path: 'form', msg: 'form 必须是 JSON 对象（八段声明）' })
    return out
  }
  const f = form as Record<string, unknown>
  // 2) 八段键白名单（越界键拒绝——DSL 闭合，防声明走私）
  const allowed = new Set<string>(FORM_SECTION_KEYS)
  for (const k of Object.keys(f)) {
    if (!allowed.has(k)) {
      out.push({ path: `form.${k}`, msg: `form.${k} 不在八段白名单（${FORM_SECTION_KEYS.join('/')}）` })
    }
  }
  // 3) 三段字段行：key/label/uiType 必填、uiType 白名单、同段 key 唯一
  const keysBySection = new Map<string, Set<string>>()
  for (const sec of FIELD_SECTIONS) {
    const rows = asArr(f[sec])
    const seen = new Map<string, number>()
    rows.forEach((r, i) => {
      const o = asObj(r)
      const p = `form.${sec}[${i}]`
      const key = String(o.key ?? '')
      if (!key.trim()) out.push({ path: `${p}.key`, msg: `${p}.key 必填` })
      if (!String(o.label ?? '').trim()) out.push({ path: `${p}.label`, msg: `${p}.label 必填` })
      const ui = String(o.uiType ?? '')
      if (!UI_TYPE_SET.has(ui)) {
        out.push({ path: `${p}.uiType`, msg: `${p}.uiType「${ui || '(空)'}」不在 9 基元白名单` })
      }
      if (key) {
        if (seen.has(key)) {
          out.push({ path: `${p}.key`, msg: `${sec} 段 key「${key}」重复（第 ${seen.get(key)! + 1}/${i + 1} 行）` })
        } else {
          seen.set(key, i)
        }
      }
    })
    keysBySection.set(sec, new Set(seen.keys()))
  }
  const allKeys = new Set<string>()
  for (const sec of FIELD_SECTIONS) for (const k of keysBySection.get(sec) ?? []) allKeys.add(k)

  // 4) conditions：op 白名单 + when.field/show 引用存在
  asArr(f.conditions).forEach((r, i) => {
    const o = asObj(r)
    const p = `form.conditions[${i}]`
    const when = asObj(o.when)
    const op = String(when.op ?? '')
    if (!OP_SET.has(op)) {
      out.push({ path: `${p}.when.op`, msg: `${p}.when.op「${op || '(空)'}」不在操作符白名单（${SPEC_OPS.join('/')}）` })
    }
    const wf = String(when.field ?? '')
    if (wf && !allKeys.has(wf)) pushRefViolation(out, `${p}.when.field`, '条件字段', wf)
    for (const k of asArr(o.show).map(String)) {
      if (!allKeys.has(k)) pushRefViolation(out, `${p}.show`, '条件显示', k)
    }
  })

  // 5) constraints：type 白名单 + field 引用存在
  asArr(f.constraints).forEach((r, i) => {
    const o = asObj(r)
    const p = `form.constraints[${i}]`
    const t = String(o.type ?? '')
    if (!CONSTRAINT_SET.has(t)) {
      out.push({ path: `${p}.type`, msg: `${p}.type「${t || '(空)'}」不在约束类型白名单（${CONSTRAINT_TYPES.join('/')}）` })
    }
    const fd = String(o.field ?? '')
    if (fd && !allKeys.has(fd)) pushRefViolation(out, `${p}.field`, '约束目标', fd)
  })

  // 6) exclusions：when.field / exclude.field 引用存在
  asArr(f.exclusions).forEach((r, i) => {
    const o = asObj(r)
    const p = `form.exclusions[${i}]`
    const wf = String(asObj(o.when).field ?? '')
    if (wf && !allKeys.has(wf)) pushRefViolation(out, `${p}.when.field`, '排除条件', wf)
    const ef = String(asObj(o.exclude).field ?? '')
    if (ef && !allKeys.has(ef)) pushRefViolation(out, `${p}.exclude.field`, '排除目标', ef)
  })

  // 7) refs：field 引用存在 + scopes ⊆ 五域
  asArr(f.refs).forEach((r, i) => {
    const o = asObj(r)
    const p = `form.refs[${i}]`
    const fd = String(o.field ?? '')
    if (fd && !allKeys.has(fd)) pushRefViolation(out, `${p}.field`, '引用变量域', fd)
    for (const sc of asArr(o.scopes).map(String)) {
      if (!SCOPE_SET.has(sc)) {
        out.push({ path: `${p}.scopes`, msg: `${p}.scopes 含未知域「${sc}」（白名单：${REF_SCOPES.join('/')}）` })
      }
    }
  })

  // 8) exports：from 枚举；from=log 必有 logKey
  asArr(f.exports).forEach((r, i) => {
    const o = asObj(r)
    const p = `form.exports[${i}]`
    const from = String(o.from ?? '')
    if (!EXPORT_FROM_SET.has(from)) {
      out.push({ path: `${p}.from`, msg: `${p}.from「${from || '(空)'}」不在枚举（${EXPORT_FROMS.join('/')}）` })
    }
    if (from === 'log' && !String(o.logKey ?? '').trim()) {
      out.push({ path: `${p}.logKey`, msg: `${p}.logKey 缺失：from=log 必须声明日志行键名` })
    }
  })

  // 9) lineage：role/pick/assetType 合法（lineage 缺省按空处理，宽松）
  if (s.lineage !== undefined && s.lineage !== null) {
    if (typeof s.lineage !== 'object' || Array.isArray(s.lineage)) {
      out.push({ path: 'lineage', msg: 'lineage 必须是 JSON 对象' })
    } else {
      const assets = (s.lineage as Record<string, unknown>).assets
      if (assets !== undefined && assets !== null && !Array.isArray(assets)) {
        out.push({ path: 'lineage.assets', msg: 'lineage.assets 必须是数组' })
      } else if (Array.isArray(assets)) {
        assets.forEach((r, i) => {
          const o = asObj(r)
          const p = `lineage.assets[${i}]`
          const role = String(o.role ?? '')
          if (!ASSET_ROLE_SET.has(role)) {
            out.push({ path: `${p}.role`, msg: `${p}.role「${role || '(空)'}」非法（source/target）` })
          }
          if (!String(o.pick ?? '').trim()) {
            out.push({ path: `${p}.pick`, msg: `${p}.pick 必填（资产拾取声明）` })
          }
          const at = String(o.assetType ?? '')
          if (!ASSET_TYPE_SET.has(at)) {
            out.push({ path: `${p}.assetType`, msg: `${p}.assetType「${at || '(空)'}」非法（${LINEAGE_ASSET_TYPES.join('/')}）` })
          }
        })
      }
    }
  }
  return out
}

/* ================= 旧声明 diff（diffSummary） ================= */

export interface DiffSummaryResult {
  /** 旧 formFields 字段数（按 key 去重前） */
  oldCount: number
  /** 新八段三段字段键数（去重） */
  newCount: number
  /** 已迁移：旧字段 key 仍出现在新三段 */
  migrated: string[]
  /** 待语义分析：旧字段 key 未出现在新三段（不允许静默丢弃，须逐个人工裁决） */
  pending: string[]
}

/** 旧→新 diff 概览：旧字段 key 仍出现在新三段 = migrated，其余 = pending（待语义分析） */
export function diffSummary(oldFormFields: unknown[], spec: BaselineSpec): DiffSummaryResult {
  const olds = (Array.isArray(oldFormFields) ? oldFormFields : [])
    .map((x) => (x !== null && typeof x === 'object' ? (x as Record<string, unknown>).key : undefined))
    .filter((k): k is string => typeof k === 'string' && k !== '')
  const newKeys = new Set(allFieldKeys(spec))
  const migrated: string[] = []
  const pending: string[] = []
  for (const k of olds) (newKeys.has(k) ? migrated : pending).push(k)
  return { oldCount: olds.length, newCount: newKeys.size, migrated, pending }
}

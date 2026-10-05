/**
 * M1 B4：组件声明 spec 类型 + 纯数据校验（红线 2 前端镜像）。
 *
 * 与后端 api/component_design.py validate_spec_pure_data 同口径：
 * - 递归扫描字段名与字符串值，命中禁用片段（函数/代码/模板语法）即违规——
 *   设计器「打字即校验」行内红标的主闸门（后端 422 为第二道兜底）；
 * - 数值含 NaN/Infinity 违规（后端 json.dumps allow_nan=False 同语义；
 *   JS JSON.stringify 会静默把 NaN 变 null，必须在编辑期拦住）；
 * - dropPolicy.autoName 占位符白名单仅 {type}/{n}（治理设计 §11）。
 * 声明结构对齐《组件管理与发布治理设计》§10.1（fields[].uiType=声明控件类型）。
 * V2 增量（方案§2.2）：声明式 outputs/badge/behaviors/extensions 等扩展，全部 optional
 * （旧 spec 不携带即视为未声明，normalizeSpec 归一后缺位键不落入 JSON，向后兼容）。
 * 纯函数、无副作用，可独立单测。
 */
import { TYPE_COMPAT, type DataType } from '../graph/model/portTypes'

/** 禁用片段（与后端 FORBIDDEN_SNIPPETS 逐项一致；键检查含大小写不敏感兜底） */
export const FORBIDDEN_SNIPPETS = [
  'function', '=>', 'eval(', 'new Function', 'Function(',
  '<script', 'javascript:', '__import__', 'import ', 'import(',
  'def ', 'lambda ', 'require(', 'module.exports',
  'exec(', 'subprocess', 'os.system', 'child_process',
  '${', '`',
] as const

/** autoName 允许的占位符（§11：{type} 组件 type、{n} 实例序号） */
const ALLOWED_PLACEHOLDERS = new Set(['type', 'n'])

/** 单条违规：path 定位到声明内位置（fields[0].label / dropPolicy.autoName / icon…），msg 为人类可读描述 */
export interface SpecViolation {
  path: string
  msg: string
}

function scan(node: unknown, path: string, out: SpecViolation[]): void {
  if (node !== null && typeof node === 'object' && !Array.isArray(node)) {
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
      const keyPath = path ? `${path}.${k}` : k
      const low = k.toLowerCase()
      for (const s of FORBIDDEN_SNIPPETS) {
        if (k.includes(s) || low.includes(s.toLowerCase())) {
          out.push({ path: keyPath, msg: `字段名含代码片段「${s}」: ${keyPath}` })
          break
        }
      }
      scan(v, keyPath, out)
    }
  } else if (Array.isArray(node)) {
    node.forEach((v, i) => scan(v, `${path}[${i}]`, out))
  } else if (typeof node === 'string') {
    for (const s of FORBIDDEN_SNIPPETS) {
      if (node.includes(s)) {
        out.push({ path, msg: `${path || '声明'} 含代码片段「${s}」` })
        break
      }
    }
  } else if (typeof node === 'number' && !Number.isFinite(node)) {
    out.push({ path, msg: `${path || '声明'} 含非严格 JSON 数值（NaN/Infinity）` })
  }
}

/** 纯数据校验（打字即校验真源）：返回违规清单（空数组 = 通过） */
export function validateSpecPureData(spec: unknown): SpecViolation[] {
  if (spec === null || typeof spec !== 'object' || Array.isArray(spec)) {
    return [{ path: '', msg: '声明必须是 JSON 对象' }]
  }
  const out: SpecViolation[] = []
  scan(spec, '', out)
  const dp = (spec as Record<string, unknown>).dropPolicy
  const autoName = dp !== null && typeof dp === 'object' ? (dp as Record<string, unknown>).autoName : undefined
  if (typeof autoName === 'string') {
    for (const m of autoName.match(/\{([^{}]*)\}/g) ?? []) {
      const ph = m.slice(1, -1)
      if (!ALLOWED_PLACEHOLDERS.has(ph)) {
        out.push({ path: 'dropPolicy.autoName', msg: `dropPolicy.autoName 占位符 {${ph}} 不在白名单（仅允许 {type}/{n}）` })
      }
    }
  }
  return out
}

/* ================= 声明结构（治理设计 §10.1；编辑器规范化形态） ================= */

/** 声明控件类型白名单：B3 收敛的 FieldKind 9 基元（§10.2 白名单可执行化的 M1 落地） */
export const SPEC_UI_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'number', label: '数值' },
  { value: 'bool', label: '开关' },
  { value: 'select', label: '下拉' },
  { value: 'expr', label: '表达式' },
  { value: 'hint', label: '提示' },
  { value: 'rows', label: '行编辑表' },
  { value: 'mapEditor', label: '映射编辑' },
  { value: 'resource', label: '资源选择' },
] as const

export type SpecUiType = (typeof SPEC_UI_TYPES)[number]['value']
const SPEC_UI_TYPE_SET = new Set<string>(SPEC_UI_TYPES.map((t) => t.value))

export interface SpecPort {
  name: string
  type: string
}

/** 表单字段声明（纯数据；showIf 为声明式条件 JSON，运行时按 DSL 判定，初版仅语法校验） */
export interface SpecField {
  key: string
  label: string
  uiType: SpecUiType
  required: boolean
  /** 默认值（编辑器文本输入；非字符串存量值原样保留，编辑后才变为字符串） */
  default?: unknown
  desc: string
  /** select 静态候选（仅 select 声明携带——normField 条件展开，非 select 不落该键，故可选） */
  options?: { label: string; value: string | number }[]
  showIf?: unknown
  /** V2 新增：三层归属（缺省视为 required，向后兼容） */
  layer?: 'required' | 'optional' | 'hidden'
  /** V2 新增：声明式控件选项（数值范围/占位/多行/远端候选源） */
  optionsEx?: { min?: number; max?: number; step?: number; placeholder?: string
               multiline?: boolean; remote?: string }
}

export interface SpecDropPolicy {
  snapToGrid: boolean
  autoName: string
  /** drop 时一次性快照预填的字段 key（§11 划界语义：与 Inspector pick 实时联动并存） */
  prefillFromUpstream: string[]
  autoConnect: { upstream: 'nearest' | 'none'; downstream: 'nearest' | 'none' }
  /** 单工作流实例上限（0 = 不限） */
  maxInstances: number
}

/** 组件声明（spec 级内容；身份字段 type/name/profile/executionModel 等在主表，不随 spec 保存） */
export interface ComponentSpec {
  icon: string
  color: string
  summary: string
  ports: { inputs: SpecPort[]; outputs: SpecPort[] }
  fields: SpecField[]
  dropPolicy: SpecDropPolicy
  /** 设计态面板可见（D1 闸门 §13-5：executionModel=runtime-only 必须显式 false，仅装载物化消费） */
  paletteVisible: boolean
  /* ── V2（方案§2.2，全部 optional）── */
  /** 展示名（工作台/调色板标题优先于主表 name） */
  displayName?: string
  /** 搜索别名（调色板检索命中域扩展） */
  aliases?: string[]
  /** 长描述（Markdown；summary 的展开位） */
  description?: string
  /** 调色板分组路径（如「批处理与同步/数据源」） */
  category?: string
  /** 外部文档链接 */
  docUrl?: string
  /** 声明式输出（数据面语义，供连线类型推断/预览消费；区别于 ports 的物理端口） */
  outputs?: { name: string; type: DataType; desc?: string }[]
  /** 状态徽标（key=字段名，colorMap=值→颜色） */
  badge?: { key: string; colorMap: Record<string, string> }
  /** 声明式行为 */
  behaviors?: {
    onChange?: { field: string; action: 'refreshOptions'|'resetFields'|'prefill'; target?: string[]; remote?: string }[]
    prefillFromUpstream?: { field: string; from: 'input.table'|'input.columns'|'input.datasource' }[]
    pick?: { field: string; picker: 'table'|'column'|'cron'|'sshHost' }[]
  }
  /** 扩展能力（运行时消费，不进表单） */
  extensions?: {
    hiddenInputs?: ('tenantId'|'runId'|'nodeId'|'workflowId')[]
    capabilities?: { testable?: boolean; previewLimit?: number }
  }
  /** 声明 schema 版本（缺省视为 1.0 旧格式） */
  specVersion?: string
  /** 实例初始化模板（drop 时合并进字段初值） */
  initTemplate?: Record<string, unknown>
}

function normPort(v: unknown): SpecPort {
  const o = (v !== null && typeof v === 'object' ? v : {}) as Record<string, unknown>
  return { name: String(o.name ?? ''), type: String(o.type ?? '') }
}

function normField(v: unknown): SpecField {
  const o = (v !== null && typeof v === 'object' ? v : {}) as Record<string, unknown>
  const rawUi = String(o.uiType ?? '')
  const uiType = (SPEC_UI_TYPE_SET.has(rawUi) ? rawUi : 'text') as SpecUiType
  const options = Array.isArray(o.options)
    ? o.options.map((x) => {
        const r = (x !== null && typeof x === 'object' ? x : {}) as Record<string, unknown>
        return { label: String(r.label ?? ''), value: typeof r.value === 'string' || typeof r.value === 'number' ? r.value : String(r.value ?? '') }
      })
    : []
  const layer = (typeof o.layer === 'string' && FIELD_LAYERS.has(o.layer) ? o.layer : 'required') as NonNullable<SpecField['layer']>
  const optionsEx = normOptionsEx(o.optionsEx)
  return {
    key: String(o.key ?? ''),
    label: String(o.label ?? ''),
    uiType,
    required: o.required === true,
    default: o.default,
    desc: String(o.desc ?? ''),
    ...(uiType === 'select' ? { options } : {}),
    ...(o.showIf !== undefined ? { showIf: o.showIf } : {}),
    layer,
    ...(optionsEx !== undefined ? { optionsEx } : {}),
  }
}

/* ── V2（方案§2.2）新字段归一：非法值兜底，归一后缺位键不落入结果对象 ── */

/** DataType 运行时白名单（由 TYPE_COMPAT 键 + any/none 派生，与 portTypes 枚举保持同源不双写） */
const DATA_TYPE_SET = new Set<string>(['any', 'none', ...Object.keys(TYPE_COMPAT)])
const FIELD_LAYERS = new Set(['required', 'optional', 'hidden'])
const ONCHANGE_ACTIONS = new Set(['refreshOptions', 'resetFields', 'prefill'])
const PREFILL_FROMS = new Set(['input.table', 'input.columns', 'input.datasource'])
const PICKERS = new Set(['table', 'column', 'cron', 'sshHost'])
const HIDDEN_INPUT_KEYS = new Set(['tenantId', 'runId', 'nodeId', 'workflowId'])

/** 松散 JSON 对象守卫（后端 spec 本就是松散 JSON，入参一律按 unknown 兜底） */
function isPlainObj(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

type SpecOutputDecl = NonNullable<ComponentSpec['outputs']>[number]
type BehaviorOnChangeDecl = NonNullable<NonNullable<ComponentSpec['behaviors']>['onChange']>[number]
type BehaviorPrefillDecl = NonNullable<NonNullable<ComponentSpec['behaviors']>['prefillFromUpstream']>[number]
type BehaviorPickDecl = NonNullable<NonNullable<ComponentSpec['behaviors']>['pick']>[number]
type HiddenInputKey = NonNullable<NonNullable<ComponentSpec['extensions']>['hiddenInputs']>[number]

/** 宽松透传字符串（类型校验兜底：非字符串 → 缺位） */
function normOptString(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined
}

/** 别名数组：非数组缺位；元素非字符串过滤 */
function normAliases(v: unknown): string[] | undefined {
  if (!Array.isArray(v)) return undefined
  return v.filter((x): x is string => typeof x === 'string')
}

/** 声明式输出：type 不在 DataType 枚举 → 归一为 any（不炸渲染） */
function normOutputs(v: unknown): ComponentSpec['outputs'] {
  if (!Array.isArray(v)) return undefined
  return v.map((x) => {
    const o = isPlainObj(x) ? x : {}
    const t = String(o.type ?? '')
    const item: SpecOutputDecl = { name: String(o.name ?? ''), type: (DATA_TYPE_SET.has(t) ? t : 'any') as DataType }
    if (typeof o.desc === 'string') item.desc = o.desc
    return item
  })
}

/** 状态徽标：key/colorMap 结构校验，颜色值仅保留字符串 */
function normBadge(v: unknown): ComponentSpec['badge'] {
  if (!isPlainObj(v) || typeof v.key !== 'string' || !isPlainObj(v.colorMap)) return undefined
  const colorMap: Record<string, string> = {}
  for (const [k, val] of Object.entries(v.colorMap)) {
    if (typeof val === 'string') colorMap[k] = val
  }
  return { key: v.key, colorMap }
}

/** 声明式行为：逐项枚举校验，非法项丢弃 */
function normBehaviors(v: unknown): ComponentSpec['behaviors'] {
  if (!isPlainObj(v)) return undefined
  const out: NonNullable<ComponentSpec['behaviors']> = {}
  if (Array.isArray(v.onChange)) {
    out.onChange = v.onChange.flatMap((x): BehaviorOnChangeDecl[] => {
      const o = isPlainObj(x) ? x : {}
      if (typeof o.field !== 'string' || typeof o.action !== 'string' || !ONCHANGE_ACTIONS.has(o.action)) return []
      const item: BehaviorOnChangeDecl = { field: o.field, action: o.action as BehaviorOnChangeDecl['action'] }
      if (Array.isArray(o.target)) item.target = o.target.filter((t): t is string => typeof t === 'string')
      if (typeof o.remote === 'string') item.remote = o.remote
      return [item]
    })
  }
  if (Array.isArray(v.prefillFromUpstream)) {
    out.prefillFromUpstream = v.prefillFromUpstream.flatMap((x): BehaviorPrefillDecl[] => {
      const o = isPlainObj(x) ? x : {}
      if (typeof o.field !== 'string' || typeof o.from !== 'string' || !PREFILL_FROMS.has(o.from)) return []
      return [{ field: o.field, from: o.from as BehaviorPrefillDecl['from'] }]
    })
  }
  if (Array.isArray(v.pick)) {
    out.pick = v.pick.flatMap((x): BehaviorPickDecl[] => {
      const o = isPlainObj(x) ? x : {}
      if (typeof o.field !== 'string' || typeof o.picker !== 'string' || !PICKERS.has(o.picker)) return []
      return [{ field: o.field, picker: o.picker as BehaviorPickDecl['picker'] }]
    })
  }
  return out
}

/** 扩展能力：hiddenInputs 只保留 4 个合法枚举；previewLimit 硬约束 ≤100（Math.min 兜底） */
function normExtensions(v: unknown): ComponentSpec['extensions'] {
  if (!isPlainObj(v)) return undefined
  const out: NonNullable<ComponentSpec['extensions']> = {}
  if (Array.isArray(v.hiddenInputs)) {
    out.hiddenInputs = v.hiddenInputs.filter((x): x is HiddenInputKey =>
      typeof x === 'string' && HIDDEN_INPUT_KEYS.has(x))
  }
  if (isPlainObj(v.capabilities)) {
    const c = v.capabilities
    const caps: NonNullable<NonNullable<ComponentSpec['extensions']>['capabilities']> = {}
    if (typeof c.testable === 'boolean') caps.testable = c.testable
    const limit = Number(c.previewLimit)
    if (Number.isFinite(limit)) caps.previewLimit = Math.min(limit, 100)
    out.capabilities = caps
  }
  return out
}

/** 声明式控件选项：数值域 Number 兜底，全部非法 → 缺位 */
function normOptionsEx(v: unknown): SpecField['optionsEx'] {
  if (!isPlainObj(v)) return undefined
  const num = (x: unknown): number | undefined => {
    const n = Number(x)
    return Number.isFinite(n) ? n : undefined
  }
  const out: NonNullable<SpecField['optionsEx']> = {}
  const min = num(v.min)
  if (min !== undefined) out.min = min
  const max = num(v.max)
  if (max !== undefined) out.max = max
  const step = num(v.step)
  if (step !== undefined) out.step = step
  if (typeof v.placeholder === 'string') out.placeholder = v.placeholder
  if (v.multiline === true) out.multiline = true
  if (typeof v.remote === 'string') out.remote = v.remote
  return Object.keys(out).length > 0 ? out : undefined
}

/** 服务端 spec → 编辑器规范化骨架（冻结空草稿 {} 也能得到完整可编辑形态） */
export function normalizeSpec(raw: unknown): ComponentSpec {
  const s = (raw !== null && typeof raw === 'object' && !Array.isArray(raw) ? raw : {}) as Record<string, unknown>
  const ports = (s.ports !== null && typeof s.ports === 'object' ? s.ports : {}) as Record<string, unknown>
  const dp = (s.dropPolicy !== null && typeof s.dropPolicy === 'object' ? s.dropPolicy : {}) as Record<string, unknown>
  const ac = (dp.autoConnect !== null && typeof dp.autoConnect === 'object' ? dp.autoConnect : {}) as Record<string, unknown>
  const maxRaw = Number(dp.maxInstances)
  const displayName = normOptString(s.displayName)
  const aliases = normAliases(s.aliases)
  const description = normOptString(s.description)
  const category = normOptString(s.category)
  const docUrl = normOptString(s.docUrl)
  const outputs = normOutputs(s.outputs)
  const badge = normBadge(s.badge)
  const behaviors = normBehaviors(s.behaviors)
  const extensions = normExtensions(s.extensions)
  const specVersion = normOptString(s.specVersion)
  const initTemplate = isPlainObj(s.initTemplate) ? s.initTemplate : undefined
  return {
    icon: String(s.icon ?? ''),
    color: String(s.color ?? ''),
    summary: String(s.summary ?? ''),
    ports: {
      inputs: Array.isArray(ports.inputs) ? ports.inputs.map(normPort) : [],
      outputs: Array.isArray(ports.outputs) ? ports.outputs.map(normPort) : [],
    },
    fields: Array.isArray(s.fields) ? s.fields.map(normField) : [],
    dropPolicy: {
      snapToGrid: dp.snapToGrid === true,
      autoName: String(dp.autoName ?? ''),
      prefillFromUpstream: Array.isArray(dp.prefillFromUpstream) ? dp.prefillFromUpstream.map(String) : [],
      autoConnect: {
        upstream: ac.upstream === 'none' ? 'none' : 'nearest',
        downstream: ac.downstream === 'none' ? 'none' : 'nearest',
      },
      maxInstances: Number.isFinite(maxRaw) && maxRaw > 0 ? Math.floor(maxRaw) : 0,
    },
    paletteVisible: s.paletteVisible === false ? false : true,
    /* ── V2（方案§2.2）：非法值缺位（键不落入 JSON），旧 spec 不受影响 ── */
    ...(displayName !== undefined ? { displayName } : {}),
    ...(aliases !== undefined ? { aliases } : {}),
    ...(description !== undefined ? { description } : {}),
    ...(category !== undefined ? { category } : {}),
    ...(docUrl !== undefined ? { docUrl } : {}),
    ...(outputs !== undefined ? { outputs } : {}),
    ...(badge !== undefined ? { badge } : {}),
    ...(behaviors !== undefined ? { behaviors } : {}),
    ...(extensions !== undefined ? { extensions } : {}),
    ...(specVersion !== undefined ? { specVersion } : {}),
    ...(initTemplate !== undefined ? { initTemplate } : {}),
  }
}

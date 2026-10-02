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
 * 纯函数、无副作用，可独立单测。
 */

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
  return {
    key: String(o.key ?? ''),
    label: String(o.label ?? ''),
    uiType,
    required: o.required === true,
    default: o.default,
    desc: String(o.desc ?? ''),
    ...(uiType === 'select' ? { options } : {}),
    ...(o.showIf !== undefined ? { showIf: o.showIf } : {}),
  }
}

/** 服务端 spec → 编辑器规范化骨架（冻结空草稿 {} 也能得到完整可编辑形态） */
export function normalizeSpec(raw: unknown): ComponentSpec {
  const s = (raw !== null && typeof raw === 'object' && !Array.isArray(raw) ? raw : {}) as Record<string, unknown>
  const ports = (s.ports !== null && typeof s.ports === 'object' ? s.ports : {}) as Record<string, unknown>
  const dp = (s.dropPolicy !== null && typeof s.dropPolicy === 'object' ? s.dropPolicy : {}) as Record<string, unknown>
  const ac = (dp.autoConnect !== null && typeof dp.autoConnect === 'object' ? dp.autoConnect : {}) as Record<string, unknown>
  const maxRaw = Number(dp.maxInstances)
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
  }
}

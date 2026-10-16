/**
 * FE 契约适配层 — 共享机械原语模块（仅新增文件，不改动 9 个 RED 契约 .ts）。
 * 设计依据：docs/increments/2026-10-16-FE契约适配层设计.md §3.2 混合式（共享机械原语 + 每 API 文件薄映射层）。
 *
 * 职责（R4-SYNC Q12 已裁定：snake↔camel 字段名映射与 project/datasource 数值 ID、
 * plan/run 字符串 ID 的归一化放 FE service adapter 层；RED 契约签名保持不动）：
 *   - §2.1 命名映射：snake_case ↔ camelCase 深度递归（仅键名级；字符串值一律透传，R1.3）
 *   - §2.2 id 归一：wire ↔ FE number/string 的无损转换与校验（R2.1–R2.4；uuid→number 有损 fail-fast，R2.3）
 *   - §2.4 归一错误类型：ContractApiError（R4.1；R2.3 有损 id 转换抛错的统一载体）
 *
 * 明确不做（语义加工负面清单，设计文档 §1.3）：
 *   - 不做计数推导（targetWritten = inserted + updated 等，挂 R4-SYNC Q7，待冻结确认）
 *   - 不做枚举值词形映射（cancel_requested ↔ cancelling 等，Q9 已裁定词形落 FE 契约/页面层）
 *   - 不做成功包络解包/错误码改写（§2.3 包络是否全域统一待 Codex，开放问题 1，属 GREEN 接线期条目）
 *   - 不做 DTO 字段登记表（R1.1 每 API 文件映射表属 GREEN 接线期，与契约类型同文件演进）
 *   - 不接线任何哨兵/页面；不含 fetch。
 *
 * 前置约定：处理 JSON 形态数据（BE 响应经 JSON 解析、FE 请求为 plain DTO），不含循环引用；
 * 非 plain object（Date/Map/Set/FormData 等类实例）整体透传、不遍历其内部键。
 * 未发生任何变化的子树按原引用返回（避免不必要的对象创建）；调用方不得原地修改返回值。
 */

/* ---------- §2.4 R4.1 归一错误类型 ---------- */

/** id 归一失败的统一错误码（适配层本地错误，httpStatus 约定为 0） */
export const ID_NORMALIZATION_FAILED = 'ID_NORMALIZATION_FAILED'

export interface ContractApiErrorInit {
  /** HTTP 状态码；非 HTTP 来源的适配层本地错误（如 id 归一失败）为 0 */
  httpStatus: number
  /** BE 错误码（number，如 4001）或适配层本地错误码（string，如 ID_NORMALIZATION_FAILED） */
  code: number | string
  msg: string
  /** 原始载荷/原始值，仅诊断用；UI 不得依赖其结构 */
  raw?: unknown
}

/**
 * 适配层归一错误（§2.4 R4.1）：传输层失败与 id 归一失败统一以 rejected promise 携带本类型，
 * 与 RED 契约方法「异步 rejected promise」形态一致（UI 捕获方式不因接线改变）。
 * 注意：本仓库 tsconfig 启用 erasableSyntaxOnly，禁用构造器参数属性语法。
 */
export class ContractApiError extends Error {
  readonly httpStatus: number
  readonly code: number | string
  readonly msg: string
  readonly raw?: unknown

  constructor(init: ContractApiErrorInit) {
    super(init.msg)
    this.name = 'ContractApiError'
    this.httpStatus = init.httpStatus
    this.code = init.code
    this.msg = init.msg
    if (init.raw !== undefined) {
      this.raw = init.raw
    }
  }
}

/* ---------- §2.1 命名映射：snake_case ↔ camelCase ---------- */

/**
 * snake_case → camelCase 键名（单键，通用规则 R1.2 的键级形态）。
 * 保守规则（fail-visible，不猜测词形，R1.4）：
 *  - 无下划线短键原样（db / sql / name）；
 *  - 含大写、前导/尾随/连续下划线的键视为非标准 snake，原样返回；
 *  - 仅纯小写 snake_case 参与转换（rows_read → rowsRead、watermark_column → watermarkColumn）。
 */
export function snakeToCamelKey(key: string): string {
  if (!key.includes('_')) return key
  if (/[A-Z]/.test(key)) return key
  if (key.startsWith('_') || key.endsWith('_') || key.includes('__')) return key
  const segments = key.split('_')
  const first = segments[0]
  if (first === undefined || first === '') return key
  let out = first
  for (let i = 1; i < segments.length; i++) {
    const segment = segments[i] ?? ''
    out += segment.charAt(0).toUpperCase() + segment.slice(1)
  }
  return out
}

/**
 * camelCase → snake_case 键名（单键，请求方向 FE→BE，R1.6 的通用词形规则）。
 * 保守规则（fail-visible）：
 *  - 无 camel 边界（全小写、全大写缩写、前导大写）原样返回；
 *  - 含连续大写（缩写词，如 SQLText）不做猜测性拆分，原样返回；
 *  - 仅标准 camel 边界（小写/数字后跟大写）参与转换（rowsTotal → rows_total、rowsIn → rows_in）。
 */
export function camelToSnakeKey(key: string): string {
  if (!/[a-z0-9][A-Z]/.test(key)) return key
  if (/[A-Z][A-Z]/.test(key)) return key
  return key.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase()
}

type KeyConverter = (key: string) => string

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const proto: unknown = Object.getPrototypeOf(value)
  return proto === Object.prototype || proto === null
}

/** 深度递归键名转换：数组与 plain object 递归；其余值（含 string，R1.3）按引用透传 */
function convertDeep(value: unknown, convertKey: KeyConverter): unknown {
  if (Array.isArray(value)) {
    let changed = false
    const out: unknown[] = new Array(value.length)
    for (let i = 0; i < value.length; i++) {
      const item = value[i]
      const converted = convertDeep(item, convertKey)
      if (converted !== item) changed = true
      out[i] = converted
    }
    return changed ? out : value
  }
  if (isPlainObject(value)) {
    const out: Record<string, unknown> = {}
    let changed = false
    for (const key of Object.keys(value)) {
      const nextKey = convertKey(key)
      const item = value[key]
      const converted = convertDeep(item, convertKey)
      if (nextKey !== key || converted !== item) changed = true
      out[nextKey] = converted
    }
    return changed ? out : value
  }
  return value
}

/** 响应方向 BE→FE：键名 snake_case → camelCase 深度转换（嵌套对象与数组递归，R1.2；字符串值透传，R1.3） */
export function snakeToCamel<T>(value: T): T {
  return convertDeep(value, snakeToCamelKey) as T
}

/** 请求方向 FE→BE：键名 camelCase → snake_case 深度转换（嵌套对象与数组递归） */
export function camelToSnake<T>(value: T): T {
  return convertDeep(value, camelToSnakeKey) as T
}

/* ---------- §2.2 id 归一：wire ↔ FE number/string ---------- */

const DECIMAL_INTEGER_PATTERN = /^-?\d+$/

/** 构造 id 归一失败错误（R2.3：有损即拒绝，禁止截断/哈希/本地重映射表） */
function lossyIdError(field: string, value: unknown): ContractApiError {
  const shown = typeof value === 'string' ? `"${value}"` : String(value)
  return new ContractApiError({
    httpStatus: 0,
    code: ID_NORMALIZATION_FAILED,
    msg: `cannot losslessly normalize wire id for field "${field}" (R2.3 lossy conversion rejected): ${shown}`,
    raw: value,
  })
}

/**
 * wire id → FE number id（FE 契约字段为 number 时使用，如 SyncPlanVersion.planId、SyncRunSummary.runId）。
 * 接受两种 wire 形态（R2.3 无损判据）：
 *  - JSON number：须 Number.isSafeInteger；
 *  - JSON string：须纯十进制整数字面量（拒绝 uuid/十六进制/指数/空白）、无前导零
 *    （"007"→7 往返失真，违反 R2.4 对账一致性）、且数值落在安全整数范围内。
 * 任何不满足情形抛 ContractApiError（fail-fast），绝不静默截断。
 */
export function wireIdToNumber(value: unknown, field: string): number {
  if (typeof value === 'number') {
    if (Number.isSafeInteger(value)) return value
    throw lossyIdError(field, value)
  }
  if (typeof value === 'string') {
    if (!DECIMAL_INTEGER_PATTERN.test(value)) throw lossyIdError(field, value)
    if (value.length > 1 && (value.charAt(0) === '0' || (value.charAt(0) === '-' && value.charAt(1) === '0'))) {
      throw lossyIdError(field, value)
    }
    const parsed = Number(value)
    if (!Number.isSafeInteger(parsed)) throw lossyIdError(field, value)
    return parsed
  }
  throw lossyIdError(field, value)
}

/** FE number id → wire string（R2.2 无损正向：String(id)；非安全整数 fail-fast） */
export function numberToWireId(value: number, field: string): string {
  if (Number.isSafeInteger(value)) return String(value)
  throw lossyIdError(field, value)
}

/**
 * wire id → FE string id（FE 契约字段为 string 时使用，如 LineageWritebackEntry.runId、StreamJobRow.jobId、
 * SqlExecuteRequest 返回的 taskId）。
 * 字符串原样透传（不 trim、不改大小写，R2.4 对账一致性）；空串视为非法（空 id 无法定位任何实体，R4.4 fail-visible）；
 * BE 以 JSON number 下发的数值 id 仅在安全整数范围内无损转 string。
 */
export function wireIdToString(value: unknown, field: string): string {
  if (typeof value === 'string') {
    if (value.length === 0) throw lossyIdError(field, value)
    return value
  }
  if (typeof value === 'number' && Number.isSafeInteger(value)) return String(value)
  throw lossyIdError(field, value)
}

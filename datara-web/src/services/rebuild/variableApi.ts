/**
 * R2（统一变量体系）契约层 — GREEN 接线（接线计划 Task 2，R2 批次）。
 * 端点与映射依据：docs/increments/2026-10-17-R系列GREEN接线计划.md §1.1 原语 + Task 2 契约面表；
 * 包络 {code,msg,data} 已实证固化（datara-backend rebuild 域全域 + rebuild/variables/api.py _success/_error）。
 * 本文件语义源自 docs/increments/2026-10-14-datara-platform-rebuild-design.md §5（设计真源）：
 * 统一语法 ${scope.name}（global/project/workflow/task/env/run/tmp + $[时间表达式]）、
 * 七级优先级链 run > task > workflow > project > global > env > builtin、
 * 表单八项能力（语法校验/补全/类型提示/现值预览/来源展示/未定义/类型不匹配/循环引用检测）、
 * 运行快照表 task_instance_variable_runtime（表达式/作用域/变量名/解析值/类型/来源/解析时间/attempt）。
 * R2_VARIABLE_NOT_WIRED 常量保留（View 横幅引用兼容）；引用语法解析等纯前端逻辑不变（见 VariableValidationView）。
 */

import { camelToSnake, camelToSnakeKey, ContractApiError, snakeToCamel } from './adapterKit'
import { getToken } from '../http'

/* ---------- 作用域与类型（设计 §5 真源，后端冻结前不改） ---------- */

/** 七级解析优先级链（设计差异注记 6：本链为设计真源，收窄须用户批准） */
export const VARIABLE_SCOPE_PRIORITY = ['run', 'task', 'workflow', 'project', 'global', 'env', 'builtin'] as const

/** 语法前缀集合（设计 §5）：七级链作用域 + tmp 临时作用域 */
export type VariableScope = (typeof VARIABLE_SCOPE_PRIORITY)[number] | 'tmp'

/** 值类型草案（设计要求“变量类型”能力，具体枚举以后端契约为权威） */
export type VariableValueType = 'string' | 'number' | 'boolean' | 'json'

/* ---------- 变量定义与清单 ---------- */

export interface VariableDefinition {
  scope: VariableScope
  name: string
  valueType: VariableValueType
  value: string
  description?: string
  /** 敏感值按原设计范围处理（纠偏设计 §2.2：不引入额外秘密管理范围） */
  sensitive?: boolean
}

export interface VariableCompletionItem {
  scope: VariableScope
  name: string
  valueType: VariableValueType
  /** 当前可解析值；不可用时为 null 并由 reason 说明 */
  currentValue: string | null
  unavailableReason?: string
}

/* ---------- 引用校验与解析预览 ---------- */

export type VariableDiagnosticCode = 'SYNTAX' | 'UNDEFINED' | 'TYPE_MISMATCH' | 'SCOPE_INVISIBLE' | 'CYCLE'

export interface VariableDiagnostic {
  code: VariableDiagnosticCode
  message: string
}

export interface ReferenceCheckResult {
  expression: string
  valid: boolean
  diagnostics: VariableDiagnostic[]
}

export interface ResolutionPreview {
  expression: string
  /** 现时解析值；不可用时为 null 并由 diagnostics 说明原因 */
  resolvedValue: string | null
  source?: { scope: VariableScope; name: string }
  diagnostics: VariableDiagnostic[]
}

/* ---------- 运行快照（task_instance_variable_runtime，设计 §5） ---------- */

export interface VariableSnapshotEntry {
  expression: string
  scope: VariableScope
  name: string
  resolvedValue: string
  valueType: VariableValueType
  source: string
  resolvedAt: string
  attemptNo: number
}

/* ---------- RED 哨兵 ---------- */

export const R2_VARIABLE_NOT_WIRED = 'R2_VARIABLE_NOT_WIRED: rebuild/variables contract not connected yet'

/** 契约方法清单（测试与 UI 横幅共用，保持单一事实源） */
export const R2_VARIABLE_CONTRACT_METHODS = [
  'listVariables',
  'saveVariable',
  'completeVariables',
  'checkReference',
  'previewResolution',
  'getRunSnapshot',
] as const

export type R2VariableContractMethod = (typeof R2_VARIABLE_CONTRACT_METHODS)[number]

/** 引用校验上下文：决定作用域可见性与类型检查基线（后端冻结前为草案语义） */
export interface VariableContext {
  projectId: number
  workflowId?: number
  workflowVersion?: number
  taskId?: string
  attemptNo?: number
}

export interface VariableContract {
  listVariables: (projectId: number, scopes?: VariableScope[]) => Promise<VariableDefinition[]>
  saveVariable: (projectId: number, definition: VariableDefinition) => Promise<{ saved: true; scope: VariableScope; name: string }>
  completeVariables: (prefix: string, context: VariableContext) => Promise<VariableCompletionItem[]>
  checkReference: (expression: string, context: VariableContext) => Promise<ReferenceCheckResult>
  previewResolution: (expression: string, context: VariableContext) => Promise<ResolutionPreview>
  getRunSnapshot: (instanceId: number, attemptNo?: number) => Promise<VariableSnapshotEntry[]>
}

/* ---------- GREEN 统一原语（接线计划 §1.1；R2 固化 {code,msg,data} 包络层，其余批次沿用） ---------- */

/** 端点前缀（Task 2 契约面表） */
const BASE = '/api/v1/rebuild/variables'

const TIMEOUT_MS = 15000

/** 后端成功包络（rebuild 域全域实证形态） */
interface ApiEnvelope {
  code?: number
  msg?: string
  data?: unknown
}

/** 统一 JSON fetch 原语：15s AbortController 超时 + token header（'token'，与 http.ts 同源）+ 包络解包 + 归一错误 */
async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const token = getToken()
    if (token) headers.token = token
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { ...headers, ...(init?.headers as Record<string, string>) },
      signal: ctrl.signal,
    })
    if (!res.ok) {
      const raw = await res.text().catch(() => '')
      throw new ContractApiError({ httpStatus: res.status, code: res.status, msg: `HTTP ${res.status} ${path}`, raw })
    }
    const envelope = (await res.json()) as ApiEnvelope
    if (typeof envelope.code === 'number' && envelope.code !== 0 && envelope.code !== 200) {
      throw new ContractApiError({ httpStatus: res.status, code: envelope.code, msg: envelope.msg ?? path, raw: envelope })
    }
    return (envelope.data ?? envelope) as T
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ContractApiError({ httpStatus: 0, code: 'TIMEOUT', msg: `请求超时（${TIMEOUT_MS / 1000}s）${path}` })
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

/** GET：查询键 camel→snake 序列化（undefined 值剔除），响应深度 snake→camel */
async function getJson<T>(path: string, query?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const qs = query
    ? '?' +
      Object.entries(query)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => `${encodeURIComponent(camelToSnakeKey(k))}=${encodeURIComponent(String(v))}`)
        .join('&')
    : ''
  return snakeToCamel(await requestJson<unknown>(`${path}${qs}`)) as T
}

/** POST/PUT：请求体深度 camel→snake，响应深度 snake→camel */
async function sendJson<T>(method: 'POST' | 'PUT', path: string, body: unknown): Promise<T> {
  return snakeToCamel(await requestJson<unknown>(path, { method, body: JSON.stringify(camelToSnake(body)) })) as T
}

/**
 * R2 变量契约工厂 — GREEN：6 方法接线至 P1 冻结契约的后端实现（Task 2 契约面表），
 * 签名与返回类型不动，UI 层（VariableValidationView）不感知切换。
 */
export function createVariableContract(): VariableContract {
  return {
    listVariables: (projectId, scopes) =>
      getJson<VariableDefinition[]>('', { projectId, scopes: scopes?.join(',') }),
    saveVariable: async (projectId, definition) => {
      const saved = await sendJson<{ saved?: boolean; scope: VariableScope; name: string }>(
        'POST',
        `?project_id=${projectId}`,
        definition,
      )
      if (!saved || saved.saved !== true) {
        throw new ContractApiError({
          httpStatus: 200,
          code: 'CONTRACT_VIOLATION',
          msg: `saveVariable 响应缺少 saved:true（POST ${BASE}?project_id=${projectId}）`,
          raw: saved,
        })
      }
      return { saved: true, scope: saved.scope, name: saved.name }
    },
    completeVariables: (prefix, context) =>
      sendJson<VariableCompletionItem[]>('POST', '/complete', { prefix, context }),
    checkReference: (expression, context) =>
      sendJson<ReferenceCheckResult>('POST', '/check-reference', { expression, context }),
    previewResolution: (expression, context) =>
      sendJson<ResolutionPreview>('POST', '/preview', { expression, context }),
    getRunSnapshot: (instanceId, attemptNo) =>
      getJson<VariableSnapshotEntry[]>('/run-snapshot', { instanceId, attemptNo }),
  }
}

/* ---------- 纯前端逻辑：引用语法解析（设计 §5 语法校验的本地部分） ---------- */

const REF_PATTERN = /\$\{([a-zA-Z]+)\.([a-zA-Z0-9_.]+)\}/g
const TIME_PATTERN = /\$\[([^\]]*)\]/g

export interface ParsedReferences {
  /** ${scope.name} 引用（保留出现顺序与去重） */
  refs: Array<{ scope: string; name: string }>
  /** $[...] 时间表达式 */
  timeExpressions: string[]
  /** 无法归类的 ${...} 片段（未知作用域前缀或缺失点号） */
  syntaxErrors: string[]
}

/** 本地解析文本中的变量引用与时间表达式：仅做语法归类，语义校验以服务端 checkReference 为准 */
export function parseVariableReferences(text: string): ParsedReferences {
  const refs: ParsedReferences['refs'] = []
  const seen = new Set<string>()
  const timeExpressions: string[] = []
  const syntaxErrors: string[] = []
  const scopes = new Set<string>([...VARIABLE_SCOPE_PRIORITY, 'tmp'])

  for (const match of text.matchAll(REF_PATTERN)) {
    const scope = match[1]
    const name = match[2]
    const key = `${scope}.${name}`
    if (!seen.has(key)) {
      seen.add(key)
      refs.push({ scope, name })
    }
  }
  for (const match of text.matchAll(TIME_PATTERN)) {
    timeExpressions.push(match[1])
  }
  // 语法错误：形如 ${...} 但不属于合法引用，也不与 $[...] 时间表达式重叠
  for (const match of text.matchAll(/\$\{([^}]*)\}/g)) {
    const inner = match[1]
    const dot = inner.indexOf('.')
    const scope = dot > 0 ? inner.slice(0, dot) : ''
    const name = dot > 0 ? inner.slice(dot + 1) : ''
    if (!scope || !name || !scopes.has(scope)) {
      syntaxErrors.push(`\${${inner}}`)
    }
  }
  return { refs, timeExpressions, syntaxErrors }
}

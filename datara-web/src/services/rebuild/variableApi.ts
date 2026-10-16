/**
 * R2（统一变量体系）契约层 — RED 阶段。
 * 端点前缀为草案（/api/v1/rebuild/variables/*），最终以后端契约为权威；
 * 本文件语义源自 docs/increments/2026-10-14-datara-platform-rebuild-design.md §5（设计真源）：
 * 统一语法 ${scope.name}（global/project/workflow/task/env/run/tmp + $[时间表达式]）、
 * 七级优先级链 run > task > workflow > project > global > env > builtin、
 * 表单八项能力（语法校验/补全/类型提示/现值预览/来源展示/未定义/类型不匹配/循环引用检测）、
 * 运行快照表 task_instance_variable_runtime（表达式/作用域/变量名/解析值/类型/来源/解析时间/attempt）。
 * RED 约定：所有 I/O 方法在后端接入前抛 R2_VARIABLE_NOT_WIRED，不发出任何真实请求；
 * 引用语法解析等纯前端逻辑可真实运行（见 VariableValidationView）。
 */

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

/* ---------- RED 实现（后端接入前统一抛哨兵；方法清单见 R2_VARIABLE_CONTRACT_METHODS） ---------- */

/** 异步契约方法统一实现：rejected promise（同步 throw 会在调用点直接炸出，无法被 rejects 断言捕获） */
const notWired = async (): Promise<never> => {
  throw new Error(R2_VARIABLE_NOT_WIRED)
}

/**
 * R2 变量契约工厂（原型态）：签名与类型已冻结，实现在后端就绪后按本接口逐方法替换，
 * UI 层（VariableValidationView）不感知切换。
 */
export function createVariableContract(): VariableContract {
  return {
    listVariables: notWired,
    saveVariable: notWired,
    completeVariables: notWired,
    checkReference: notWired,
    previewResolution: notWired,
    getRunSnapshot: notWired,
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

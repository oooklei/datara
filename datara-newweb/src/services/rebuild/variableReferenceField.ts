/**
 * L5-04 准备段：变量引用到业务表单输入位的消费契约。
 *
 * 本文件只定义可由业务表单消费的类型面与纯映射逻辑。实际按钮、诊断展示和
 * Playwright 五码验收须在 L5-02/L5-03 提供真实输入位后接入，不在此创建孤立 UI。
 */
import type {
  ReferenceCheckResult,
  VariableContext,
  VariableContract,
  VariableDiagnostic,
  VariableDiagnosticCode,
  VariableValueType,
} from './variableApi'

/** 服务端 `/check-reference` 冻结的完整诊断码集合。 */
export const VARIABLE_REFERENCE_DIAGNOSTIC_CODES = [
  'SYNTAX',
  'UNDEFINED',
  'TYPE_MISMATCH',
  'SCOPE_INVISIBLE',
  'CYCLE',
] as const satisfies readonly VariableDiagnosticCode[]

/** UI 必须原样展示 code，并可使用此字典补充稳定中文标题。 */
export const VARIABLE_REFERENCE_DIAGNOSTIC_LABELS: Readonly<Record<VariableDiagnosticCode, string>> = {
  SYNTAX: '语法错误',
  UNDEFINED: '变量未定义',
  TYPE_MISMATCH: '类型不匹配',
  SCOPE_INVISIBLE: '作用域不可见',
  CYCLE: '循环引用',
}

/** 可承载变量引用的业务表单输入形态；不把普通用户名等文本字段自动纳入。 */
export type VariableReferenceInputKind = 'text' | 'textarea' | 'script' | 'sql' | 'expression' | 'variable'

/**
 * 由各业务表单显式登记的输入位。surfaceId + fieldPath 构成全域扫描稳定键，
 * 禁止依据控件标签或所有 text 输入做隐式推断。
 */
export interface VariableReferenceFieldDescriptor {
  surfaceId: string
  fieldPath: string
  label: string
  inputKind: VariableReferenceInputKind
  expectedValueType?: VariableValueType
  allowScopedReference: true
  allowTimeExpression: boolean
}

/** L5-04 对消费方冻结的交互能力；按钮必须由用户显式触发。 */
export interface VariableReferenceFieldCapabilities {
  checkTrigger: 'explicit-button'
  checkMethod: 'checkReference'
  diagnosticCodes: typeof VARIABLE_REFERENCE_DIAGNOSTIC_CODES
  diagnosticPresentation: 'explicit-code-and-message'
}

export interface VariableReferenceFieldContract {
  descriptor: Readonly<VariableReferenceFieldDescriptor>
  capabilities: Readonly<VariableReferenceFieldCapabilities>
}

export type VariableReferenceCheckStatus = 'valid' | 'invalid'

/** 供按钮消费层直接渲染的稳定结果；不吞掉未知消息或合并多个诊断。 */
export interface VariableReferenceCheckViewModel {
  fieldKey: string
  expression: string
  status: VariableReferenceCheckStatus
  diagnostics: Array<VariableDiagnostic & { label: string }>
}

const CAPABILITIES: VariableReferenceFieldCapabilities = {
  checkTrigger: 'explicit-button',
  checkMethod: 'checkReference',
  diagnosticCodes: VARIABLE_REFERENCE_DIAGNOSTIC_CODES,
  diagnosticPresentation: 'explicit-code-and-message',
}

function requiredText(value: string, name: string): string {
  const normalized = value.trim()
  if (!normalized) throw new TypeError(`${name} must not be empty`)
  return normalized
}

/** 业务表单注册输入位时调用；返回值可安全作为 schema 元数据保存。 */
export function defineVariableReferenceField(
  descriptor: VariableReferenceFieldDescriptor,
): VariableReferenceFieldContract {
  const normalized: VariableReferenceFieldDescriptor = {
    ...descriptor,
    surfaceId: requiredText(descriptor.surfaceId, 'surfaceId'),
    fieldPath: requiredText(descriptor.fieldPath, 'fieldPath'),
    label: requiredText(descriptor.label, 'label'),
  }
  return { descriptor: Object.freeze(normalized), capabilities: CAPABILITIES }
}

export function variableReferenceFieldKey(descriptor: VariableReferenceFieldDescriptor): string {
  return `${descriptor.surfaceId}:${descriptor.fieldPath}`
}

/**
 * 显式校验按钮的唯一动作入口。网络错误继续抛给表单统一错误层；业务诊断逐项保留。
 */
export async function checkVariableReferenceField(
  contract: VariableReferenceFieldContract,
  expression: string,
  context: VariableContext,
  variableContract: Pick<VariableContract, 'checkReference'>,
): Promise<VariableReferenceCheckViewModel> {
  const result: ReferenceCheckResult = await variableContract.checkReference(expression, context)
  return {
    fieldKey: variableReferenceFieldKey(contract.descriptor),
    expression: result.expression,
    status: result.valid ? 'valid' : 'invalid',
    diagnostics: result.diagnostics.map((diagnostic) => ({
      ...diagnostic,
      label: VARIABLE_REFERENCE_DIAGNOSTIC_LABELS[diagnostic.code],
    })),
  }
}

/**
 * 组件 spec 表单八段 DSL 的轻类型与段访问器（L12 组件声明规范：spec 纯 JSON）。
 *
 * 活体 spec（GET /api/v1/rebuild/components/spec）实证形状：
 *  - inputs/outputs/params：FieldDef { key, label, uiType, required, visible, default?, options?, cap?, ... }；
 *  - conditions：显隐规则 { id, when: {field, op, value}, show: string[] }；
 *  - constraints：值域约束 { field, type: 'requiredIf', value: {field, op, value}, msg }；
 *  - refs：变量引用域 { field, scopes: string[] }；exports：导出端口 { key, from, type, desc }。
 * 六区块（①输入~⑥排除）框架层只消费前六段；段元素形状不做强校验（后端冻结契约），
 * 无法识别的元素按原样透传为描述行。
 */
import type { ComponentSpecItem, FormSection } from './componentSpecApi'

export interface SpecFieldDef {
  key: string
  label?: string
  uiType?: string
  required?: boolean
  visible?: boolean
  default?: unknown
  options?: { label?: string; value?: unknown }[]
  cap?: { mode?: string; max?: number; [k: string]: unknown }
  [k: string]: unknown
}

/** when 条件算子（conditions/constraints 共用，纯数据无函数） */
export interface SpecWhen {
  field: string
  op: 'eq' | 'ne' | string
  value?: unknown
}

export interface SpecConditionRule {
  id?: string
  when: SpecWhen
  show: string[]
}

export interface SpecConstraint {
  field: string
  type: string
  value?: SpecWhen
  msg?: string
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 取 spec.form 指定段（八段冻结数组，缺段按空处理） */
export function sectionOf(spec: ComponentSpecItem | null | undefined, section: FormSection): unknown[] {
  const raw = spec?.form?.[section]
  return Array.isArray(raw) ? raw : []
}

export function fieldDefsOf(spec: ComponentSpecItem | null | undefined, section: FormSection): SpecFieldDef[] {
  return sectionOf(spec, section).filter(isRecord) as SpecFieldDef[]
}

export function conditionsOf(spec: ComponentSpecItem | null | undefined): SpecConditionRule[] {
  return sectionOf(spec, 'conditions').filter(isRecord) as unknown as SpecConditionRule[]
}

export function constraintsOf(spec: ComponentSpecItem | null | undefined): SpecConstraint[] {
  return sectionOf(spec, 'constraints').filter(isRecord) as unknown as SpecConstraint[]
}

/** when 条件求值（validator #10 组件级约束与条件面板共用；op: eq/ne） */
export function evalWhen(when: SpecWhen | undefined, params: Record<string, unknown> | null | undefined): boolean {
  if (!when || !isRecord(params)) return false
  const actual = params[when.field]
  return when.op === 'ne' ? actual !== when.value : actual === when.value
}

/** requiredIf 约束求值：when 命中且字段为空（undefined/null/''）即违规 */
export function constraintViolations(
  spec: ComponentSpecItem | null | undefined,
  params: Record<string, unknown> | null | undefined,
): SpecConstraint[] {
  if (!isRecord(params)) return []
  return constraintsOf(spec).filter((rule) => rule.type === 'requiredIf' && evalWhen(rule.value, params) && isEmptyValue(params[rule.field]))
}

function isEmptyValue(value: unknown): boolean {
  return value === undefined || value === null || value === ''
}

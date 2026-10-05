/**
 * Task 6（方案§2.1/§2.6）：组件声明 8 要素 → 4 组完整度纯函数。
 *
 * 4 组口径：身份 = type/displayName/aliases/summary/description/category/docUrl；
 * 契约 = fields + outputs；表现 = icon/color/badge + behaviors；扩展 = dropPolicy/extensions/initTemplate/specVersion。
 * 缺项判定（组完成度以「拖入落库与连线可用的最低门槛」为准，非逐要素清点）：
 * - 身份：type（草稿创建时生成）与 summary 必填；
 * - 契约：至少一个 required 字段（f.required===true 或 f.layer==='required'，layer 缺省视为 required
 *   是 Task 2 既定语义）；逻辑组件（page/canvas-device 等无数据输出语义者，由调用方判型传入）
 *   豁免 outputs——其余数据组件须声明 outputs（连线类型推断消费，方案§2.3）；
 * - 表现：icon（palette 呈现）；color/badge 不设门槛；
 * - 扩展：恒完成（全部可选，无门槛）。
 * canDrop = 身份齐 ∧ 表现齐（方案§2.1 拖入落库最低门槛；契约缺项只提示不阻塞拖入）。
 * 纯函数、无副作用，可独立单测。
 */

export type CompletenessGroupId = 'identity' | 'contract' | 'visual' | 'extension'

export interface CompletenessGroup {
  id: CompletenessGroupId
  done: boolean
  missing: string[]
}

export interface CompletenessResult {
  groups: CompletenessGroup[]
  /** 全部缺项 key 的扁平清单（顺序 = 组序） */
  missing: string[]
  /** 拖入落库最低门槛（方案§2.1）：身份齐 ∧ 表现齐 */
  canDrop: boolean
}

/** 完整度判定输入（宽松子集形状：type 来自 draft 主表，其余来自 spec 分片） */
export interface CompletenessSpecInput {
  type?: string
  summary?: string
  icon?: string
  color?: string
  fields?: { required?: boolean; layer?: string }[]
  outputs?: unknown[]
  /** true = 逻辑组件（页面/画布元件等无数据输出语义），豁免 outputs 缺项 */
  logical?: boolean
}

/** required 判定口径（Task 2 既定语义：layer 缺省视为 required） */
export function isRequiredField(f: { required?: boolean; layer?: string }): boolean {
  return f.required === true || f.layer === 'required'
}

export function specCompleteness(spec: CompletenessSpecInput): CompletenessResult {
  const identityMissing: string[] = []
  if (!spec.type) identityMissing.push('type')
  if (!spec.summary) identityMissing.push('summary')

  const contractMissing: string[] = []
  if (!(spec.fields ?? []).some(isRequiredField)) contractMissing.push('fields.required')
  if (!spec.logical && (spec.outputs ?? []).length === 0) contractMissing.push('outputs')

  const visualMissing: string[] = []
  if (!spec.icon) visualMissing.push('icon')

  const groups: CompletenessGroup[] = [
    { id: 'identity', missing: identityMissing, done: identityMissing.length === 0 },
    { id: 'contract', missing: contractMissing, done: contractMissing.length === 0 },
    { id: 'visual', missing: visualMissing, done: visualMissing.length === 0 },
    { id: 'extension', missing: [], done: true },
  ]
  return {
    groups,
    missing: groups.flatMap((g) => g.missing),
    canDrop: identityMissing.length === 0 && visualMissing.length === 0,
  }
}

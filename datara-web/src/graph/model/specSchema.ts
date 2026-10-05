/**
 * spec 驱动渲染的视图适配层（工作台优化 Task 5，方案 §2.3，R1 风险对策）。
 *
 * ComponentSpec（声明编辑形态，services/componentSpec）与 NodeSchema（profile 渲染形态，
 * profiles/types）结构不同：resolveNodeSchema 在 spec 命中且可用时把 spec 适配成
 * NodeSchema 视图，否则回落 profile.nodeTypes——两源并存，profile 仍是主数据源，
 * spec 命中才驱动，不做一次性替换。
 *
 * 依赖方向（零循环硬约束）：本文件对 profiles/types 与 services/componentSpec 均为
 * import type（编译期擦除），运行时零依赖；graph/model/index.ts re-export 本模块
 * 不引入运行时环（profiles/types → ../model 亦为 import type）。
 *
 * 适配口径（宁可缺省不可编造，缺位键直接省略）：
 * - label = displayName ?? summary，desc = summary，icon/color 直传；
 * - form：fields 映射 FieldSchema（key/label 直传、uiType→type 恒等映射——SPEC_UI_TYPES
 *   九基元本就是 B3 收敛后 FieldKind 的子集、required 直传、select options 的 value
 *   收敛为 string 值域）；layer==='hidden' 的字段排除（hidden 语义：不进表单，
 *   运行时注入，不占拖入初值）；fields[].default 汇总进 schema.defaults——
 *   FieldSchema 无默认值位，NodeSchema.defaults 是拖入初值的既有承载（applyInitTemplate 消费）；
 * - spec.outputs（{name,type,desc} 声明式输出）与 NodeSchema.outputs（{id,label} 端口）
 *   形态不兼容，省略；spec.category（字符串分组路径）与 categories（枚举数组）不兼容，
 *   省略——palette 分组仍由 profile.palette 驱动；
 * - code/shape/branches/ports/dropPolicy 等 spec 无对应位，一律缺省省略。
 */
import type { FieldSchema, NodeSchema, ViewProfile } from '../profiles/types'
import type { ComponentSpec } from '../../services/componentSpec'

/** ComponentSpec → NodeSchema 视图适配（纯函数；type 取 specMap 键，spec 自身无 type 字段） */
export function specToSchema(type: string, spec: ComponentSpec): NodeSchema {
  const form: FieldSchema[] = []
  const defaults: Record<string, unknown> = {}
  for (const f of spec.fields) {
    if (f.layer === 'hidden') continue
    const fs: FieldSchema = { key: f.key, label: f.label, type: f.uiType, required: f.required }
    if (f.uiType === 'select' && f.options) {
      fs.options = f.options.map((o) => ({ value: String(o.value), label: o.label }))
    }
    form.push(fs)
    if (f.default !== undefined) defaults[f.key] = f.default
  }
  return {
    type,
    label: spec.displayName ?? spec.summary,
    icon: spec.icon,
    color: spec.color,
    desc: spec.summary,
    ...(Object.keys(defaults).length > 0 ? { defaults } : {}),
    form,
  }
}

/** 节点类型 schema 解析（两源并存）：spec 命中且启用 → spec 视图；否则 profile 兜底（可 undefined，不抛错） */
export function resolveNodeSchema(
  type: string,
  profile: Pick<ViewProfile, 'nodeTypes'>,
  specMap: ReadonlyMap<string, ComponentSpec>,
  specEnabled: boolean,
): NodeSchema | undefined {
  if (specEnabled) {
    const spec = specMap.get(type)
    if (spec) return specToSchema(type, spec)
  }
  return profile.nodeTypes[type]
}

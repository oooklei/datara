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
 * 适配口径（宁可缺省不可编造，逐键取舍）：
 * - label = displayName ?? summary，desc = summary，icon/color 直传；
 * - form：fields 映射 FieldSchema（key/label 直传、uiType→type 恒等映射——SPEC_UI_TYPES
 *   九基元本就是 B3 收敛后 FieldKind 的子集、required 直传、select options 的 value
 *   收敛为 string 值域，select 恒落 options 键与 normField 产物一致——可为空数组）；
 *   layer==='hidden' 的字段排除（hidden 语义：不进表单，运行时注入，不占拖入初值）；
 *   fields[].default 汇总进 schema.defaults——FieldSchema 无默认值位，NodeSchema.defaults
 *   是拖入初值的既有承载（applyInitTemplate 优先级链的最低级）；
 * - dropPolicy：只映射运行时被消费的键——decideDrop 读 maxInstances（>0 拦截，
 *   0 与缺省等价故 0 不落）、prefillFromUpstream（非空数组才落，GraphWorkbench 拖入链
 *   上游快照预填）；snapToGrid/autoName/autoConnect 在 NodeSchema.dropPolicy 无对应位
 *   亦无消费点，不映射。两键皆空 → 整键省略；
 * - initTemplate：spec 扁平 Record<字段key, 初值> → NodeSchema {props} 形态
 *   （applyInitTemplate 仅消费 initTemplate?.props）；ComponentInitTemplate.rect 全仓
 *   无读取点且 spec 无来源，缺位不编造（编译期 as 断言仅收口类型，运行时只读 props）；
 *   空模板整键省略；
 * - spec.outputs（{name,type,desc} 声明式输出）与 NodeSchema.outputs（{id,label} 端口）
 *   形态不兼容，省略；spec.category（字符串分组路径）与 categories（枚举数组）不兼容，
 *   省略——palette 分组仍由 profile.palette 驱动；
 * - code/shape/branches/ports 等 spec 无对应位，一律缺省省略。
 *
 * memo：specMap 值已 markRaw（引用稳定），视图按 spec 弱引用缓存——同 spec 恒返回同一
 * 视图对象（也固化了 type 键；specMap 每类型一条，无二义）。spec 整体替换（200 重建）
 * 后旧 spec 失去引用，WeakMap 条目随之可 GC，无泄漏。视图对象 markRaw 固化：
 * data.schema 全链只读（DataNode 读 shape、Inspector/DropConfigDialog 只收 prop），
 * 免去 flowNode data 深代理开销。
 */
import { markRaw } from 'vue'
import type { ComponentInitTemplate, DeclaredBehaviors, FieldSchema, NodeSchema, ResourcePick, ViewProfile } from '../profiles/types'
import type { ComponentSpec } from '../../services/componentSpec'

/** spec → NodeSchema 视图缓存（弱引用，随 spec 生命周期回收） */
const schemaCache = new WeakMap<ComponentSpec, NodeSchema>()

/** ComponentSpec → NodeSchema 视图适配（纯函数；type 取 specMap 键，spec 自身无 type 字段） */
export function specToSchema(type: string, spec: ComponentSpec): NodeSchema {
  const cached = schemaCache.get(spec)
  if (cached) return cached
  const form: FieldSchema[] = []
  const defaults: Record<string, unknown> = {}
  const pickByField = new Map((spec.behaviors?.pick ?? []).map((item) => [item.field, item.picker]))
  const capForPick = (picker: string | undefined): ResourcePick | undefined => {
    switch (picker) {
      case 'table': return { mode: 'table' }
      case 'column': return { mode: 'column' }
      case 'sshHost': return { mode: 'runtimeNode' }
      default: return undefined
    }
  }
  for (const f of spec.fields) {
    if (f.layer === 'hidden') continue
    const cap = capForPick(pickByField.get(f.key))
    const fs: FieldSchema = { key: f.key, label: f.label, type: cap ? 'resource' : f.uiType, required: f.required, ...(cap ? { cap } : {}) }
    if (f.uiType === 'select' && f.options) {
      fs.options = f.options.map((o) => ({ value: String(o.value), label: o.label }))
    }
    form.push(fs)
    if (f.default !== undefined) defaults[f.key] = f.default
  }
  /* dropPolicy：仅运行时被消费的键（maxInstances>0 / prefillFromUpstream 非空）才落 */
  const dp = spec.dropPolicy
  const dropPolicy = dp.maxInstances > 0 || dp.prefillFromUpstream.length > 0
    ? {
        ...(dp.maxInstances > 0 ? { maxInstances: dp.maxInstances } : {}),
        ...(dp.prefillFromUpstream.length > 0 ? { prefillFromUpstream: dp.prefillFromUpstream } : {}),
      }
    : undefined
  /* initTemplate：扁平初值表 → {props}（rect 无消费点无来源，缺位；空模板省略整键） */
  const initTemplate = spec.initTemplate && Object.keys(spec.initTemplate).length > 0
    ? { props: spec.initTemplate } as ComponentInitTemplate
    : undefined
  const view: NodeSchema = markRaw({
    type,
    label: spec.displayName ?? spec.summary,
    icon: spec.icon,
    color: spec.color,
    desc: spec.summary,
    ...(Object.keys(defaults).length > 0 ? { defaults } : {}),
    ...(dropPolicy !== undefined ? { dropPolicy } : {}),
    ...(initTemplate !== undefined ? { initTemplate } : {}),
    ...(spec.behaviors ? { behaviors: spec.behaviors as DeclaredBehaviors } : {}),
    form,
  })
  schemaCache.set(spec, view)
  return view
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

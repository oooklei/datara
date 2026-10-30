/**
 * 16.1 波3 双轨轨则：对象类别 → 编辑轨分派（互斥）。
 *
 * ObjectSourceKind 13 变体（DBX 实锚 crates/dbx-types/src/types.rs L209-L223，
 * 增量 16 预研件 §2.1 亲核登记）——只覆盖「源码型对象」，不含 TABLE/INDEX
 * （表结构走独立元数据通道，索引为表子对象）。
 *
 * 轨则（A5 议程证据 L66）：kind=table → 结构化编辑轨；其余 13 变体 → 源码文本轨。
 *
 * API 可达性（fail-closed）：R5-B DdlObjectRef.kind 契约仅 5 值
 * （table/view/function/procedure/trigger，A6 冻结；BE rb_models.py ObjectRef.kind
 * 注释同域）。13 变体中仅 view/function/procedure/trigger 可直达 API；其余 9 变体
 * （materialized_view/event/sequence/synonym/job/package/package_body/type/type_body）
 * 源码轨可呈现，但写链禁用并呈现原因，候后端 kind 扩展（增量 11 交点）。
 */
import type { DdlObjectKind } from '../../../services/rebuild/sqlIdeDdlApi'

/** 源码型对象 13 变体（wire 词形 snake_case；不含 table/index）。 */
export const OBJECT_SOURCE_KINDS = [
  'view',
  'materialized_view',
  'procedure',
  'function',
  'trigger',
  'event',
  'sequence',
  'synonym',
  'job',
  'package',
  'package_body',
  'type',
  'type_body',
] as const

export type ObjectSourceKind = (typeof OBJECT_SOURCE_KINDS)[number]

/** 类别选择全集：table + 13 源码变体（14 项；INDEX 不入选择集）。 */
export const DDL_KIND_OPTIONS = ['table', ...OBJECT_SOURCE_KINDS] as const

export type DdlKindOption = (typeof DDL_KIND_OPTIONS)[number]

/** 结构化编辑轨仅 table（不得以源码编辑器代替）；null=未选择（两轨皆不派）。 */
export function isStructuredTrack(kind: DdlKindOption | null): boolean {
  return kind === 'table'
}

/** 源码文本轨 = 13 变体全集（与结构化轨互斥；null=未选择）。 */
export function isSourceTrack(kind: DdlKindOption | null): boolean {
  return kind !== null && (OBJECT_SOURCE_KINDS as readonly string[]).includes(kind)
}

/** 13 变体 → R5-B DdlObjectKind 直达映射（其余 9 变体无对应，禁链）。 */
export const API_KIND_BY_SOURCE_KIND: Partial<Record<ObjectSourceKind, DdlObjectKind>> = {
  view: 'view',
  function: 'function',
  procedure: 'procedure',
  trigger: 'trigger',
}

/** kind → R5-B API kind；不可达返回 null（UI 呈现禁链原因，fail-closed）。 */
export function toApiKind(kind: DdlKindOption): DdlObjectKind | null {
  if (kind === 'table') return 'table'
  return API_KIND_BY_SOURCE_KIND[kind] ?? null
}

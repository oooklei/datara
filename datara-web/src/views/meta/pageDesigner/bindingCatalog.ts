/**
 * 组件页面设计器 Task 8：适配性绑定候选 + placeholder 即默认值落值。
 * 与后端 api/page_designer.py GET /resources 同形（ResourceCatalog），
 * 标量槽候选 = 工作流变量 + 全局参数 + 系统时间参数；dataset 槽 = 数据源入口（ds:{id}）。
 */

/** 系统资源目录（后端 /page-designer/resources 响应镜像） */
export interface ResourceCatalog {
  datasources: { id: number; name: string; type: string; db: string }[]
  workflows: { code: number; name: string; vars: { path: string; label: string; type: string }[] }[]
  globalParams: { path: string; label: string }[]
  timeParams: { path: string; label: string; sample: string }[]
  components: { type: string; name: string; state: string; publishedVersion: number | null }[]
}
export type SlotType = 'scalar' | 'dataset'

export interface Candidate { label: string; value: string }

/** 按槽位类型推导可绑定候选：dataset → 数据源入口；scalar → 变量+参数+时间参数（组件不参与绑定）。 */
export function candidatesFor(slot: SlotType, cat: ResourceCatalog): Candidate[] {
  if (slot === 'dataset') {
    return cat.datasources.map((d) => ({ label: `${d.name}（${d.type}）`, value: `ds:${d.id}` }))
  }
  const out: Candidate[] = []
  cat.workflows.forEach((w) => w.vars.forEach((v) => out.push({ label: `${w.name}/${v.label}`, value: v.path })))
  cat.globalParams.forEach((p) => out.push({ label: `参数/${p.label}`, value: p.path }))
  cat.timeParams.forEach((t) => out.push({ label: `时间/${t.label}`, value: t.path }))
  return out
}

/** placeholder 即默认值：用户未输入时提交 placeholder 文案（BindingRef.fallback 落值口径）。 */
export function resolveFallback(placeholder: string, input: string): string {
  const trimmed = (input ?? '').trim()
  return trimmed !== '' ? trimmed : (placeholder ?? '').trim()
}

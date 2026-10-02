import { http } from './http'

export type ComponentRoute = 'master' | 'worker' | 'template' | 'nonExecutable' | 'UNROUTED'
export type ExecutionModel = 'dag-engine' | 'passthrough' | 'template' | 'demo-only' | 'canvas-device' | string

export interface ComponentRow {
  type: string
  code?: string
  label: string
  profile: string
  route: ComponentRoute
  executor: string | null
  executionModel: ExecutionModel
  executionNote: string
  categories: string[]
  paletteVisible: boolean
  runtimeOnly: boolean
  formFieldCount: number
  desc?: string | null
}

export interface ComponentStats {
  catalogHash: string
  generatedAt?: string
  stats: Record<string, any>
  profiles: Array<Record<string, any>>
}

export interface ComponentDetail extends ComponentRow {
  [key: string]: any
  dagRelevant?: boolean
  icon?: string
  color?: string
  shape?: string
  paletteGroup?: string | null
  requiredFieldCount?: number
  flags?: Record<string, unknown>
  formFields: unknown[]
  defaults?: Record<string, unknown>
}

export interface CompRegistryRow {
  type: string
  name: string
  profile: string
  scope: string
  state: string
  publishedVersion: number
  executionModel: string
  executor: string | null
  updatedAt: string | null
}

export interface ComponentCreateBody {
  type: string
  name: string
  profile?: string
  category?: string | null
  execution_model?: string
  executionModel?: string
  executor?: string | null
  description?: string | null
  spec?: Record<string, unknown>
}

export interface ComponentDraft {
  type: string
  name: string
  category?: string | null
  profile: string
  scope?: string
  executionModel: string
  executor: string | null
  executable?: boolean
  state: string
  publishedVersion: number | null
  draftRev: number
  draftVersion?: number
  description?: string | null
  tags?: string[]
  spec: Record<string, unknown>
  specHash: string
  updatedAt?: string | null
}

export interface ComponentVersionRow {
  version: number
  state: string
  specHash: string
  remark?: string | null
  publishedBy?: string | null
  publishedTime?: string | null
  publishedAt?: string | null
  createdAt?: string | null
}

export interface ComponentVersionsResult {
  type?: string
  publishedVersion?: number | null
  items: ComponentVersionRow[]
}
export interface GateItem { gate: string; ok: boolean; msg: string }
export interface FreezeResult extends ComponentVersionRow {
  frozenVersion?: number
  draftVersion?: number
}
export interface PublishResult {
  type: string
  publishedVersion: number
  specHash: string
  supersededVersion?: number | null
  publishedAt?: string | null
  gates?: GateItem[]
}
export interface ImpactedWorkflow {
  id: string
  name: string
  version: number
  releaseState: string
  refVersions: number[]
  aligned: boolean
  behind: boolean
}

export async function listComponents(params: Record<string, string | boolean | undefined> = {}): Promise<{ total: number; items: ComponentRow[]; catalogHash: string }> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') qs.set(k, String(v))
  })
  return http.get(`/components${qs.size ? `?${qs}` : ''}`)
}

export function getComponentStats(): Promise<ComponentStats> {
  return http.get('/components/stats')
}

export function getComponent(type: string): Promise<ComponentDetail> {
  return http.get(`/components/${encodeURIComponent(type)}`)
}

export function getComponentRegistry(): Promise<CompRegistryRow[]> {
  return http.get('/components/registry')
}

export function createComponentDraft(body: ComponentCreateBody): Promise<{ type: string; draftRev: number; version: number; specHash: string }> {
  const payload = { ...body, execution_model: body.execution_model ?? body.executionModel }
  return http.post('/components', payload)
}

export function getComponentDraft(type: string): Promise<ComponentDraft> {
  return http.get(`/components/${encodeURIComponent(type)}/draft`)
}

export function saveComponentDraft(type: string, body: { draftRev: number; spec: Record<string, unknown>; remark?: string }): Promise<{ type: string; draftRev: number; version: number; specHash: string }> {
  return http.put(`/components/${encodeURIComponent(type)}/draft`, {
    draft_rev: body.draftRev,
    spec: body.spec,
    remark: body.remark,
  })
}

export function listComponentVersions(type: string): Promise<ComponentVersionsResult> {
  return http.get(`/components/${encodeURIComponent(type)}/versions`)
}

export function freezeComponentVersion(type: string): Promise<FreezeResult> {
  return http.post(`/components/${encodeURIComponent(type)}/versions`, {})
}

export function publishComponentVersion(type: string, body: { version?: number; draftRev?: number; remark?: string } = {}): Promise<PublishResult> {
  return http.post(`/components/${encodeURIComponent(type)}/publish`, body)
}

export function offlineComponent(type: string): Promise<boolean> {
  return http.post(`/components/${encodeURIComponent(type)}/offline`, {})
}

export function rollbackComponent(type: string, version: number): Promise<{ type: string; publishedVersion: number }> {
  return http.post(`/components/${encodeURIComponent(type)}/rollback`, { version })
}

export async function getImpactedWorkflows(type: string): Promise<{ type: string; publishedVersion?: number; state?: string; items: ImpactedWorkflow[] }> {
  return http.get(`/components/${encodeURIComponent(type)}/impact`)
}

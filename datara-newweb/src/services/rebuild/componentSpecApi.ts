/** Component specification catalog with strong-ETag revalidation. */
import { getToken, TOKEN_HEADER } from '../http'

const ENDPOINT = '/api/v1/rebuild/components/spec'

export interface ComponentSpecItem {
  type: string
  publishedVersion: number | null
  componentRef: { type: string; version: number }
  workflowTypes: WorkflowType[]
  runtimeOnly: boolean
  identity: Record<string, unknown>
  description: Record<string, unknown>
  inputs: unknown[]
  outputs: unknown[]
  form: Record<FormSection, unknown[]>
  visual: Record<string, unknown>
  behaviors: unknown
  dropPolicy: unknown
  extensions: unknown
  specVersion: unknown
  ports: unknown
}

export type WorkflowType = 'NORMAL' | 'SYNC' | 'STREAM'
export type FormSection = 'inputs' | 'outputs' | 'params' | 'conditions' | 'constraints' | 'exclusions' | 'refs' | 'exports'

export interface ComponentSpecSnapshot {
  items: ComponentSpecItem[]
  etag: string
  source: 'network' | 'not-modified' | 'last-success'
}

const lastSuccess = new Map<string, Omit<ComponentSpecSnapshot, 'source'>>()

function validatePayload(value: unknown): { items: ComponentSpecItem[] } {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error('component specification response must be an object')
  }
  const items = (value as { items?: unknown }).items
  if (!Array.isArray(items)) throw new Error('component specification response must contain items')
  return { items: items as ComponentSpecItem[] }
}

export function resetComponentSpecCache(): void {
  lastSuccess.clear()
}

export function isDesignComponent(item: ComponentSpecItem, workflowType: WorkflowType): boolean {
  return item.runtimeOnly !== true
    && item.visual?.paletteVisible !== false
    && item.workflowTypes.includes(workflowType)
    && item.componentRef?.type === item.type
    && Number.isInteger(item.componentRef?.version)
    && item.componentRef.version >= 1
}

/**
 * Loads the authoritative catalog. A failed refresh may use only the last
 * successful response; the first load always fails closed and remains retryable.
 */
export async function loadComponentSpecs(workflowType?: WorkflowType): Promise<ComponentSpecSnapshot> {
  const cacheKey = workflowType ?? 'ALL'
  const cached = lastSuccess.get(cacheKey)
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers[TOKEN_HEADER] = token
  if (cached?.etag) headers['If-None-Match'] = cached.etag

  try {
    const url = workflowType ? `${ENDPOINT}?workflow_type=${workflowType}` : ENDPOINT
    const response = await fetch(url, { headers })
    if (response.status === 304) {
      if (!cached) throw new Error('component specification returned 304 without a cached response')
      return { ...cached, source: 'not-modified' }
    }
    if (!response.ok) throw new Error(`component specification request failed: HTTP ${response.status}`)
    const etag = response.headers.get('ETag') ?? ''
    if (!/^"[0-9a-f]{64}"$/.test(etag)) throw new Error('component specification response has no strong SHA-256 ETag')
    const { items } = validatePayload(await response.json())
    const snapshot = { items, etag }
    lastSuccess.set(cacheKey, snapshot)
    return { ...snapshot, source: 'network' }
  } catch (error) {
    if (cached) return { ...cached, source: 'last-success' }
    throw error
  }
}


/** Component specification catalog with strong-ETag revalidation. */
import { getToken, TOKEN_HEADER } from '../http'

const ENDPOINT = '/api/v1/rebuild/components/spec'

export interface ComponentSpecItem {
  type: string
  publishedVersion: number | null
  identity: Record<string, unknown>
  description: Record<string, unknown>
  inputs: unknown[]
  outputs: unknown[]
  visual: Record<string, unknown>
  behaviors: unknown
  dropPolicy: unknown
  extensions: unknown
  specVersion: unknown
  ports: unknown
}

export interface ComponentSpecSnapshot {
  items: ComponentSpecItem[]
  etag: string
  source: 'network' | 'not-modified' | 'last-success'
}

let lastSuccess: Omit<ComponentSpecSnapshot, 'source'> | undefined

function validatePayload(value: unknown): { items: ComponentSpecItem[] } {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error('component specification response must be an object')
  }
  const items = (value as { items?: unknown }).items
  if (!Array.isArray(items)) throw new Error('component specification response must contain items')
  return { items: items as ComponentSpecItem[] }
}

export function resetComponentSpecCache(): void {
  lastSuccess = undefined
}

/**
 * Loads the authoritative catalog. A failed refresh may use only the last
 * successful response; the first load always fails closed and remains retryable.
 */
export async function loadComponentSpecs(): Promise<ComponentSpecSnapshot> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers[TOKEN_HEADER] = token
  if (lastSuccess?.etag) headers['If-None-Match'] = lastSuccess.etag

  try {
    const response = await fetch(ENDPOINT, { headers })
    if (response.status === 304) {
      if (!lastSuccess) throw new Error('component specification returned 304 without a cached response')
      return { ...lastSuccess, source: 'not-modified' }
    }
    if (!response.ok) throw new Error(`component specification request failed: HTTP ${response.status}`)
    const etag = response.headers.get('ETag') ?? ''
    if (!/^"[0-9a-f]{64}"$/.test(etag)) throw new Error('component specification response has no strong SHA-256 ETag')
    const { items } = validatePayload(await response.json())
    lastSuccess = { items, etag }
    return { ...lastSuccess, source: 'network' }
  } catch (error) {
    if (lastSuccess) return { ...lastSuccess, source: 'last-success' }
    throw error
  }
}


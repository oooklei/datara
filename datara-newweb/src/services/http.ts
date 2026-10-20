export const BASE = '/api/v1' as const
export const API_BASE = BASE
export const TOKEN_KEY = 'datara_token' as const
export const HTTP_TIMEOUT_MS = 15_000 as const

export function getToken(): string {
  return globalThis.localStorage?.getItem(TOKEN_KEY) ?? ''
}

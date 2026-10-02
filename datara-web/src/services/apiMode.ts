/** Shared API mode switch for service modules and tests. */
export const apiMode: 'real' | 'mock' =
  (import.meta.env.VITE_API_MODE as 'real' | 'mock' | undefined) ?? 'real'

export const isMock = apiMode === 'mock'

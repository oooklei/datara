import type { APIRequestContext, Browser, BrowserContext } from '@playwright/test'

const BASE = 'http://192.168.1.9:18091/'

export async function login(request: APIRequestContext): Promise<string> {
  const password = process.env.E2E_PASS ?? ''
  if (!password) throw new Error('E2E_PASS 未注入：拒绝执行真实 E2E')
  const response = await request.post(new URL('/api/v1/rebuild/login', BASE).toString(), {
    data: { username: process.env.E2E_USER ?? 'e2e-runner', password },
  })
  const body = await response.json() as { code?: number; data?: { token?: string } }
  const token = body.data?.token ?? ''
  if (!response.ok() || body.code !== 0 || !token) throw new Error(`login 失败：${response.status()}/${body.code ?? '-'}`)
  return token
}

export async function authenticatedContext(browser: Browser, token: string): Promise<BrowserContext> {
  const context = await browser.newContext({ viewport: { width: 1680, height: 950 } })
  await context.addInitScript((shortLivedToken) => {
    ;(globalThis as typeof globalThis & { __DATARA_TEST_TOKEN__?: string }).__DATARA_TEST_TOKEN__ = shortLivedToken
  }, token)
  await context.route('**/api/**', (route) => {
    const headers = route.request().headers()
    return route.continue({ headers: { ...headers, token, authorization: `Bearer ${token}` } })
  })
  return context
}

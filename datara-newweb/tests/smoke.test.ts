import { describe, expect, it } from 'vitest'
import { BASE, HTTP_TIMEOUT_MS, TOKEN_KEY } from '../src/services/http'
import { routes } from '../src/router/routes'

/**
 * 工程骨架冒烟（增量 1.1-01 / 1.1-02）。
 * 单 BASE 底座常量化 + 路由红线负断言（零 demo、零验证页、不占 /api 前缀）。
 */
describe('datara-newweb 工程骨架冒烟', () => {
  it('单 BASE 底座常量化为 /api/v1', () => {
    expect(BASE).toBe('/api/v1')
  })

  it('token 键位与 15s 超时固化', () => {
    expect(TOKEN_KEY).toBe('datara_token')
    expect(HTTP_TIMEOUT_MS).toBe(15000)
  })

  it('路由为正式产品路由：零 demo、零验证页', () => {
    const paths = routes.map((r) => r.path as string)
    expect(paths.some((p) => p.includes('demo'))).toBe(false)
    expect(paths.some((p) => p.includes('validation'))).toBe(false)
    expect(paths.some((p) => p.startsWith('/api'))).toBe(false)
  })

  it('路由含登录页与首页落点（登录守卫可达）', () => {
    const paths = routes.map((r) => r.path as string)
    expect(paths).toContain('/login')
    expect(paths).toContain('/')
  })
})

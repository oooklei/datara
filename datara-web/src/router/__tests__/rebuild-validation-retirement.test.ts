/**
 * FE-03 验证页路由退役 — 深链回归机制测试
 *
 * 阶段一（当前即可跑）：深链目标可达性预检
 *   断言 10 条 /rebuild/validation/* 路由的退役映射表（RETIREMENT_PLAN.md §二）中
 *   每条 meta.deeplink 指向的正式页路由当前已注册于 routes.ts，保证退役执行时深链目标不悬空。
 *
 * 阶段二（退役执行阶段激活）：退役后回归
 *   10 条路由记录保留 + meta.retired + 组件统一指向 RetiredValidationRedirect + build 无悬空引用。
 *
 * 依据：WBS FE-03；设计 §10 融合规则；实锚 routes.ts L97-107。
 */
import { describe, expect, it } from 'vitest'
import { routes } from '../routes'

/** 退役映射表（与 RETIREMENT_PLAN.md §二 一一对应） */
const RETIREMENT_MAP: Array<{ path: string; deeplink: string }> = [
  { path: '/rebuild/validation/sql-ide-readonly', deeplink: '/ide' },
  { path: '/rebuild/validation/sql-ide-ddl', deeplink: '/ide' },
  { path: '/rebuild/validation/schedule', deeplink: '/dag/instances' },
  { path: '/rebuild/validation/stream', deeplink: '/stream/list' },
  { path: '/rebuild/validation/metrics', deeplink: '/ind/board' },
  { path: '/rebuild/validation/sync-form', deeplink: '/sync/list' },
  { path: '/rebuild/validation/dependency-form', deeplink: '/dag?tab=edit' },
  { path: '/rebuild/validation/resource-upload', deeplink: '/ds/list' },
  { path: '/rebuild/validation/variable', deeplink: '/dag?tab=edit' },
  { path: '/rebuild/validation/ai-assistant', deeplink: '/' },
]

/** 从 deeplink 中提取路由路径（去 query） */
function deeplinkPath(deeplink: string): string {
  const qIdx = deeplink.indexOf('?')
  return qIdx === -1 ? deeplink : deeplink.slice(0, qIdx)
}

/** 判断路由路径是否已注册（含静态段匹配，如 /dag 匹配 /dag?tab=edit） */
function isDeeplinkTargetRegistered(targetPath: string): boolean {
  return routes.some((r) => r.path === targetPath)
}

describe('FE-03 验证页路由退役 — 深链目标可达性预检（阶段一，当前可跑）', () => {
  it('registers all 10 /rebuild/validation/* routes', () => {
    const registered = new Set(routes.map((r) => r.path))
    for (const { path } of RETIREMENT_MAP) {
      expect(registered.has(path), `route ${path} should be registered`).toBe(true)
    }
  })

  it('has exactly 10 /rebuild/validation/* routes', () => {
    const validationRoutes = routes.filter((r) => r.path.startsWith('/rebuild/validation/'))
    expect(validationRoutes).toHaveLength(10)
  })

  it.each(RETIREMENT_MAP.map((m) => [m.path, m.deeplink] as const))(
    'deeplink target for %s (%s) is currently registered',
    (path, deeplink) => {
      const targetPath = deeplinkPath(deeplink)
      expect(
        isDeeplinkTargetRegistered(targetPath),
        `deeplink target ${targetPath} (from ${path}) should be registered in routes.ts`,
      ).toBe(true)
    },
  )

  it('keeps the retirement map in sync with the actual validation route set', () => {
    const actualPaths = routes
      .filter((r) => r.path.startsWith('/rebuild/validation/'))
      .map((r) => r.path)
      .sort()
    const mapPaths = RETIREMENT_MAP.map((m) => m.path).sort()
    expect(mapPaths).toEqual(actualPaths)
  })
})

/**
 * 阶段二：退役后回归（退役执行阶段激活）
 * 当前阶段跳过——前置（六批收口）未满足，retirement 执行未发生。
 * 退役执行时取消以下 skip，并同步实现 RETIREMENT_PLAN.md §四 的断言矩阵。
 */
describe.skip('FE-03 验证页路由退役 — 退役后回归（阶段二，待六批收口）', () => {
  it('marks all 10 validation routes as retired with deeplink', () => {
    for (const { path } of RETIREMENT_MAP) {
      const rec = routes.find((r) => r.path === path)
      expect(rec, `route ${path} should still be registered`).toBeTruthy()
      expect((rec!.meta as { retired?: boolean }).retired).toBe(true)
      expect((rec!.meta as { deeplink?: string }).deeplink).toBeTruthy()
    }
  })

  it('replaces all 10 validation components with RetiredValidationRedirect', () => {
    for (const { path } of RETIREMENT_MAP) {
      const rec = routes.find((r) => r.path === path)
      expect(rec, `route ${path} should exist`).toBeTruthy()
      const componentStr = String(rec!.component)
      expect(componentStr).toContain('RetiredValidationRedirect')
      expect(componentStr).not.toContain('/validation/variable/')
      expect(componentStr).not.toContain('/validation/stream/')
    }
  })
})

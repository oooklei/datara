import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { routes } from '../routes'

describe('isolated rebuild validation pages', () => {
  it('keeps validation pages outside the production router', () => {
    expect(routes.some((item) => item.path.startsWith('/rebuild-validation/'))).toBe(false)
  })

  it('runs Playwright against the R1 page rather than the retired R4 IDE probe', () => {
    const runner = readFileSync(new URL('../../../deploy/r1-auth-bootstrap-smoke.cjs', import.meta.url), 'utf8')

    expect(runner).toContain("'/rebuild-validation-i1.html'")
    expect(runner).not.toContain('/rebuild-validation-r4.html')
    expect(runner).toContain('created_project_id: createdProjectId')
    expect(runner).toContain('failed_requests: failedRequests')
    expect(runner).not.toMatch(/REBUILD_VALIDATION_KEY\s*=\s*['"][^'"]+['"]|X-Backend-Validation-Key\s*:\s*['"][0-9a-f]{32,}/i)
  })

  // i1/i2 均已入库；新增隔离验证页时必须同步加入本列表（credentials/存储探针逐页覆盖）。
  it.each(['i1', 'i2'])('keeps the %s validation page free of human login and prefilled credentials', (id) => {
    const html = readFileSync(new URL(`../../../public/rebuild-validation-${id}.html`, import.meta.url), 'utf8')

    expect(html).not.toMatch(/id=["'](?:username|password|login)["']/i)
    expect(html).not.toMatch(/Dev@123|datara_2026|Admin@123/)
    expect(html).toContain('__DATARA_TEST_TOKEN__')
  })
})


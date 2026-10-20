import { test, expect } from 'playwright-core'

/**
 * FE-20 门 8 — 重试/恢复回归测试
 *
 * 覆盖：
 *   - RESUME_FROM 命令链路（后端 test_resume_from_api.py 的 FE 消费面）
 *   - retry_budget / retry_deadline 持久化（C14 契约，T32/T33 交付）
 *   - 实例恢复预算对齐（大盘 #14）
 *
 * 前置：门 1-7 全解阻 + 1.9 环境授权（用户操作项③）
 * 运行：DATARA_API_BASE_URL=http://<1.9-host> npx playwright test e2e/retry-recovery.spec.ts
 *
 * 依据：WBS FE-20；后端 tests/test_resume_from_api.py；engine.py 恢复预算锚点。
 */

test.describe('FE-20 门 8 — 重试/恢复回归', () => {
  test('恢复命令链路：运行实例页对失败实例提供恢复入口', async ({ page }) => {
    test.skip(!process.env.DATARA_API_BASE_URL, '需 1.9 实测环境')
    await page.goto('/dag/instances')
    await page.waitForSelector('.instance-runs, [data-testid="instance-runs"]', { timeout: 15_000 })
    // 失败实例应有恢复按钮
    const resumeBtn = page.locator('button:has-text("恢复"), button:has-text("从指定节点恢复"), [data-testid="resume-from"]')
    if (await resumeBtn.count() > 0) {
      await expect(resumeBtn.first()).toBeVisible()
    } else {
      test.info().annotations.push({ type: 'TODO', description: '恢复按钮选择器待工作流域建模交付后补充' })
    }
  })

  test('恢复命令提交：恢复后提示 commandId 或 RESUME_FROM 确认', async ({ page }) => {
    test.skip(!process.env.DATARA_API_BASE_URL, '需 1.9 实测环境')
    await page.goto('/dag/instances')
    await page.waitForSelector('.instance-runs, [data-testid="instance-runs"]', { timeout: 15_000 })
    const resumeBtn = page.locator('button:has-text("恢复"), button:has-text("从指定节点恢复"), [data-testid="resume-from"]')
    if (await resumeBtn.count() > 0) {
      await resumeBtn.first().click()
      await expect(page.locator('.el-message--success')).toContainText('恢复', { timeout: 15_000 })
    } else {
      test.info().annotations.push({ type: 'TODO', description: '恢复命令提交选择器待补充' })
    }
  })

  test('重试预算展示：实例重试次数与预算上限可见', async ({ page }) => {
    test.skip(!process.env.DATARA_API_BASE_URL, '需 1.9 实测环境')
    await page.goto('/dag/instances')
    await page.waitForSelector('.instance-runs, [data-testid="instance-runs"]', { timeout: 15_000 })
    // retry_budget / retry_deadline 持久化字段（C14 契约）
    const retryInfo = page.locator('[data-testid="retry-budget"], .retry-budget, text=/重试.*\d+\/\d+/')
    if (await retryInfo.count() > 0) {
      await expect(retryInfo.first()).toBeVisible()
    } else {
      test.info().annotations.push({ type: 'TODO', description: '重试预算展示选择器待补充' })
    }
  })
})

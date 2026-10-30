import { expect, test, type Page } from '@playwright/test'

/**
 * S1 资源脚本编辑器能力面 E2E（真实环境 http://192.168.1.9:18091/）。
 *
 * 登录路径依用户 2026-10-29 裁定：登录页已预置演示账号，点击 [data-demo-account] 填充后提交，
 * 不注入 E2E_PASS，不读取/写入任何口令或浏览器持久存储（token 仅驻留页面内存）。
 *
 * 主用例导航走真实用户路径：登录页 → 工作台 → 项目卡片 → 项目侧栏「资源管理」。
 * 回归用例验证未认证深链：守卫探测会话触发的 401 硬跳必须带上 ?redirect=当前站内位置，
 * 登录后原地返回；token 只驻留内存，全程不整页刷新。
 *
 * 覆盖 S1 能力面的可观测外部行为：
 *  - 标题下环境状态栏（运行位置 / 语言环境 / 输出位置）；
 *  - SQL 专属「补全数据源」选择器；
 *  - `${scope.name}` 变量分色与 hover 现时解析；
 *  - 服务端静态校验结果面板；
 *  - SQL 试运行的环境语义（资源未绑定数据源 → 拒绝执行并在日志区披露原因）。
 */

const PROJECT_ID = Number(process.env.E2E_PROJECT_ID ?? '33')
const SQL_RESOURCE = process.env.E2E_SQL_RESOURCE ?? 'test-upload.sql'

async function enterResourceManagement(page: Page): Promise<void> {
  await page.goto('/login')
  const preset = page.locator('[data-demo-account]').first()
  await expect(preset).toBeVisible()
  await preset.click()
  await page.locator('form.login-form button[type="submit"]').click()
  await expect(page).toHaveURL(/\/$/)

  await page.locator(`article.project-card[data-project-id="${PROJECT_ID}"]`).click()
  await expect(page).toHaveURL(new RegExp(`/p/${PROJECT_ID}$`))

  await page.locator('[data-seg="resource-mgmt"]').click()
  await expect(page).toHaveURL(new RegExp(`/p/${PROJECT_ID}/resources$`))
}

test.describe('S1 资源脚本编辑器能力面', () => {
  test('环境状态栏 / 补全数据源 / 变量分色与 hover / 静态校验 / 试运行语义', async ({ page }) => {
    await enterResourceManagement(page)

    const row = page.locator('tbody tr', { hasText: SQL_RESOURCE })
    await expect(row).toBeVisible()
    await row.locator('[data-edit-resource]').click()

    await expect(page.locator('[data-script-editor-mask]')).toBeVisible()

    // 标题下环境状态栏：试运行发生在哪里、该语言环境是什么、结果输出到哪里
    await expect(page.locator('[data-env-bar]')).toBeVisible()
    await expect(page.locator('[data-env-location]')).toContainText('运行位置')
    await expect(page.locator('[data-env-language]')).toContainText('数据库：')
    await expect(page.locator('[data-env-output]')).toContainText('输出位置')
    // SQL 专属：表字段补全所用的数据源选择器
    await expect(page.locator('[data-completion-datasource]')).toBeVisible()

    // 变量分色：输入 ${scope.name} 后应出现变量 token 装饰
    const editor = page.locator('[data-script-code-host] .cm-content')
    await expect(editor).toBeVisible()
    await editor.click()
    await page.keyboard.press('Control+End')
    await page.keyboard.type('\n-- ${project.owner}')
    await page.keyboard.press('Escape')
    const varToken = page.locator('[data-script-code-host] .cm-var-token').first()
    await expect(varToken).toBeVisible()

    // hover：变量引用悬浮展示现时解析值（未定义时给出明确提示）
    await varToken.hover()
    await expect(page.locator('.cm-var-hover')).toBeVisible()

    // 服务端静态校验（SQL 用 sqlglot 解析，不依赖数据源连通）
    await page.locator('[data-check-script]').click()
    await expect(page.locator('[data-check-result]')).toBeVisible()

    // 试运行：SQL 资源未绑定数据源，后端拒绝执行并在日志区披露原因
    await page.locator('[data-run-script]').click()
    await expect(page.locator('[data-run-log]')).toContainText('SQL_EXECUTION_REQUIRES_DATASOURCE')
  })

  test('未认证深链 → 401 硬跳保留 redirect → 登录后原地返回', async ({ page }) => {
    const deepLink = `/p/${PROJECT_ID}/resources`

    // 直接访问深层页面：守卫探测会话拿到 401，硬跳登录页时必须把当前站内位置带进 redirect
    await page.goto(deepLink)
    await expect(page).toHaveURL(/\/login\?redirect=/)
    expect(new URL(page.url()).searchParams.get('redirect')).toBe(deepLink)

    const preset = page.locator('[data-demo-account]').first()
    await expect(preset).toBeVisible()
    await preset.click()
    await page.locator('form.login-form button[type="submit"]').click()

    // 登录后回到原目标页，而不是工作台首页
    await expect(page).toHaveURL(new RegExp(`${deepLink}$`))
    await expect(page.locator('[data-filter-keyword]')).toBeVisible()
  })
})

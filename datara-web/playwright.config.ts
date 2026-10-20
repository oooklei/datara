import { defineConfig } from 'playwright-core'

/**
 * FE-20 门 8 行为验收 — Playwright 配置
 *
 * 用例文件：e2e/gate8-behavior.spec.ts（八能力行为面）、e2e/retry-recovery.spec.ts（重试/恢复回归）
 * 前置：门 1-7 全解阻 + 1.9 环境授权（用户操作项③）
 *
 * 运行：npx playwright test（需安装 @playwright/test）
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: 1,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  // 1.9 实测环境：通过环境变量 DATARA_API_BASE_URL 切换后端端点
  // 本地开发：npm run dev（vite :5173）
  // 1.9 实测：DATARA_API_BASE_URL=http://<1.9-host>:<port> npx playwright test
})

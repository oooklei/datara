import { defineConfig, devices } from '@playwright/test'

/**
 * 真实 E2E 只能在 192.168.1.9 隔离工作目录执行。
 * 本配置不启动本机 webServer，也不从文件、URL 或浏览器存储读取凭据。
 * 各用例通过登录接口取得短时 token，并以 document-start 内存变量与请求头注入。
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [
    ['list'],
    ['json', { outputFile: 'playwright-report/results.json' }],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  outputDir: 'test-results',
  use: {
    baseURL: 'http://192.168.1.9:18091/',
    // 安全红线：报告只保留脱敏文本结果，不采集可能包含表单密钥的 trace/截图。
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})

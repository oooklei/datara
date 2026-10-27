/**
 * 增量 15.6 / LLM-01-FE 节点 B：Playwright E2E 设施（§5E 页面级验收）。
 *
 * 运行宿主：**192.168.1.9**（TEST-ENVIRONMENT-POLICY：本机禁跑任何可执行验证；
 * 1.9 前端验证入口 `http://192.168.1.9:18091/`，Web 容器内监听 80，API 代理契约不变）。
 *
 * 拓扑：**复用 1.9 已部署栈**，不另起 webServer——本票节点 A 产物构建版本由 1.9 部署栈承载
 * （见票面 environment_prerequisites）。`baseURL` 可经 `E2E_BASE` 覆盖。
 *
 * 纪律：
 *  - `workers: 1` + `fullyParallel: false`：远程测试队列单槽位，且 rebuild_llm_model 为共享可变表，
 *    并发用例会互相污染默认位/删除保护断言。
 *  - `retries: 0`：RED 与 GREEN 证据分别保留，失败 run **不得**被重跑覆盖（验收 v4）。
 *  - 鉴权：token 经 login 换取后由 `addInitScript` 注入 localStorage（document-start），
 *    值不入静态产物 / 不入 URL / 不入证据文件（红线 8 / S6）。
 */
import { defineConfig, devices } from '@playwright/test';
const BASE_URL = process.env.E2E_BASE ?? 'http://192.168.1.9:18091';
export default defineConfig({
    testDir: './e2e',
    testMatch: '**/*.spec.ts',
    /* 单用例上限：含构建后首屏 + 后端 probe（后端出站超时 10s） */
    timeout: 90_000,
    expect: { timeout: 15_000 },
    fullyParallel: false,
    forbidOnly: !!process.env.CI,
    retries: 0,
    workers: 1,
    reporter: [
        ['list'],
        ['json', { outputFile: 'playwright-report/results.json' }],
        ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ],
    outputDir: 'playwright-report',
    use: {
        baseURL: BASE_URL,
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: 'off',
        actionTimeout: 15_000,
        navigationTimeout: 30_000,
        ignoreHTTPSErrors: false,
    },
    projects: [
        { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    ],
});

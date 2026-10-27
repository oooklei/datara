const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright-core');

const BASE = 'http://192.168.1.9:18091';
const OUT = '/lei/datara/evidence/FORMAL-E2E-03';
const PROJECT_ID = 27;

function check(condition, message) {
  if (!condition) throw new Error(message);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const report = {
    ticket: 'FORMAL-E2E-03',
    baseUrl: BASE,
    deployedImage: 'ba17df2',
    capturedAt: new Date().toISOString(),
    checks: {},
    relevantResponses: [],
    consoleErrors: [],
    verdict: 'FAIL',
  };
  let browser;
  let token = '';
  let validationKey = '';
  try {
    validationKey = execFileSync('docker', ['exec', 'datara-rebuild-api', 'printenv', 'REBUILD_VALIDATION_KEY'], {
      encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    check(validationKey.length > 0, 'validation key unavailable from controlled runtime');
    const exchange = await fetch(`${BASE}/api/v1/rebuild/validation-token`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-backend-validation-key': validationKey,
        'x-backend-validation-scope': 'high-priority-e2e',
      },
      body: '{}',
    });
    const exchangeBody = await exchange.json();
    token = String(exchangeBody?.data?.token || '');
    check(exchange.status === 200 && token, `validation token exchange failed: ${exchange.status}`);
    check(exchangeBody.data.expires_in === 900, 'validation token TTL is not 900 seconds');
    report.checks.tokenExchange = {
      status: exchange.status,
      expiresIn: exchangeBody.data.expires_in,
      scope: 'high-priority-e2e',
      principal: exchangeBody.data.user?.username,
      injection: 'addInitScript + request-header route; memory only',
    };

    browser = await chromium.launch({ executablePath: chromium.executablePath(), headless: true, args: ['--no-sandbox'] });
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await context.addInitScript((shortToken) => {
      Object.defineProperty(globalThis, '__DATARA_TEST_TOKEN__', {
        value: shortToken, writable: true, configurable: true,
      });
    }, token);
    await context.route('**/api/v1/**', async (route) => {
      const headers = { ...route.request().headers(), token };
      await route.continue({ headers });
    });
    const page = await context.newPage();
    page.on('console', (msg) => {
      if (msg.type() === 'error') report.consoleErrors.push(msg.text().slice(0, 300));
    });
    page.on('response', (response) => {
      const u = response.url();
      if (/run-stats|monitor\/nodes|workflows|workflow\/definitions/.test(u)) {
        const parsed = new URL(u);
        report.relevantResponses.push({ path: parsed.pathname + parsed.search, status: response.status() });
      }
    });

    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
    const loginInputs = await page.locator('input').evaluateAll((els) => els.map((el) => ({
      type: el.getAttribute('type') || 'text', name: el.getAttribute('name') || '',
      placeholder: el.getAttribute('placeholder') || '',
    })));
    const credentialInputs = loginInputs.filter((i) => i.type === 'password' || /user|account|账号|password|密码/i.test(`${i.name} ${i.placeholder}`));
    check(credentialInputs.length === 0, 'login page exposes account/password inputs');
    report.checks.login = { url: page.url(), inputCount: loginInputs.length, credentialInputCount: 0 };
    await page.screenshot({ path: path.join(OUT, '01-login.png'), fullPage: true });

    await page.goto(`${BASE}/p/${PROJECT_ID}/dag`, { waitUntil: 'networkidle' });
    await page.locator('[data-tc-body]').waitFor({ state: 'visible', timeout: 15000 });
    const firstTask = page.locator('.pal-task:visible').first();
    check(await firstTask.count(), 'project 27 has no visible workflow candidate');
    await firstTask.click();
    await page.locator('.pal-load').click();
    await page.locator('[data-tc-canvas-workbench]').first().waitFor({ state: 'visible', timeout: 15000 });
    await page.locator('.vue-flow__node').first().waitFor({ state: 'visible', timeout: 15000 });
    const initialNodeCount = await page.locator('.vue-flow__node:visible').count();
    check(initialNodeCount > 0, 'workflow canvas has no visible nodes');

    const editorChecks = {};
    for (const item of [
      { key: 'sql', label: /SQL/i, editor: '[data-node-parameter-editor]' },
      { key: 'python', label: /Python/i, editor: '[data-node-parameter-editor]' },
      { key: 'shell', label: /Shell/i, editor: '[data-node-parameter-editor]' },
      { key: 'dependency', label: /依赖|Dependent/i, editor: '[data-dependent-editor]' },
    ]) {
      const trayButton = page.locator('.wf-tray button:visible').filter({ hasText: item.label }).first();
      check(await trayButton.count(), `${item.key} component entry is absent`);
      const before = await page.locator('.vue-flow__node').count();
      await trayButton.click();
      await page.waitForFunction((n) => document.querySelectorAll('.vue-flow__node').length > n, before);
      const node = page.locator('.vue-flow__node').last();
      await node.click();
      await page.locator(item.editor).waitFor({ state: 'visible', timeout: 5000 });
      editorChecks[item.key] = {
        trayLabel: (await trayButton.innerText()).trim(),
        editorVisible: true,
      };
    }
    report.checks.canvas = { projectId: PROJECT_ID, initialVisibleNodes: initialNodeCount, editors: editorChecks };
    await page.screenshot({ path: path.join(OUT, '02-workflow-canvas.png'), fullPage: true });

    const runStatsWait = page.waitForResponse((r) => r.url().includes('/execution/run-stats') && r.url().includes(`project_id=${PROJECT_ID}`), { timeout: 15000 });
    await page.goto(`${BASE}/p/${PROJECT_ID}/dag?tab=runs`, { waitUntil: 'domcontentloaded' });
    const runStatsResponse = await runStatsWait;
    await page.locator('[data-workflow-run-monitor]').waitFor({ state: 'visible', timeout: 15000 });
    const runPageError = await page.locator('[data-run-error]').count();
    check(runStatsResponse.status() !== 500, 'project 27 run-stats API returned 500');
    check(runStatsResponse.ok() && runPageError === 0, `project 27 monitor failed: HTTP ${runStatsResponse.status()}`);
    report.checks.project27Monitor = { apiStatus: runStatsResponse.status(), pageVisible: true, pageErrorCount: runPageError };
    await page.screenshot({ path: path.join(OUT, '03-project27-monitor.png'), fullPage: true });

    const clusterWait = page.waitForResponse((r) => r.url().includes('/rebuild/monitor/nodes'), { timeout: 15000 });
    await page.goto(`${BASE}/dep/monitor`, { waitUntil: 'domcontentloaded' });
    const clusterResponse = await clusterWait;
    await page.locator('.monitor-page').waitFor({ state: 'visible', timeout: 15000 });
    check(clusterResponse.status() !== 500 && clusterResponse.ok(), `cluster monitor API failed: ${clusterResponse.status()}`);
    report.checks.clusterMonitor = { apiStatus: clusterResponse.status(), pageVisible: true };

    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(`${BASE}/p/${PROJECT_ID}/dag?tab=runs`, { waitUntil: 'networkidle' });
    const overflow = await page.evaluate(() => ({
      viewport: innerWidth,
      htmlWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      overflow: document.documentElement.scrollWidth > innerWidth || document.body.scrollWidth > innerWidth,
    }));
    check(!overflow.overflow, `375px page-level horizontal overflow: ${JSON.stringify(overflow)}`);
    const logout = page.locator('[data-shell-logout]');
    check(await logout.isVisible(), 'logout button is not visible at 375px');
    report.checks.mobile375 = overflow;
    report.checks.logoutButton = { visible: true, text: (await logout.innerText()).trim() };
    await page.screenshot({ path: path.join(OUT, '04-mobile-375.png'), fullPage: true });

    const storageBeforeLogout = await page.evaluate(() => ({
      localKeys: Object.keys(localStorage), sessionKeys: Object.keys(sessionStorage),
      dataraTokenLocal: localStorage.getItem('datara_token'),
      dataraTokenSession: sessionStorage.getItem('datara_token'),
      runtimeInjectionPresent: Object.prototype.hasOwnProperty.call(globalThis, '__DATARA_TEST_TOKEN__'),
    }));
    check(storageBeforeLogout.dataraTokenLocal === null && storageBeforeLogout.dataraTokenSession === null, 'token found in browser persistence');
    const scriptUrls = await page.locator('script[src]').evaluateAll((els) => els.map((el) => el.src));
    let staticSecretHit = false;
    for (const scriptUrl of scriptUrls) {
      const body = await (await fetch(scriptUrl)).text();
      if (body.includes(token) || body.includes(validationKey)) staticSecretHit = true;
    }
    check(!staticSecretHit, 'token/key found in loaded static artifacts');
    check(!page.url().includes(token) && !page.url().includes(validationKey), 'token/key found in URL');
    report.checks.secretHygiene = {
      tokenInLocalStorage: false, tokenInSessionStorage: false, tokenInUrl: false,
      keyInUrl: false, staticArtifactSecretHit: false,
      runtimeInjectionConsumed: !storageBeforeLogout.runtimeInjectionPresent,
    };

    await Promise.all([
      page.waitForURL((url) => url.pathname === '/login', { timeout: 15000 }),
      logout.click(),
    ]);
    const revoked = await fetch(`${BASE}/api/v1/rebuild/projects`, { headers: { token } });
    check(revoked.status === 401, `revoked token returned HTTP ${revoked.status}`);
    report.checks.logout = { redirectedTo: new URL(page.url()).pathname, revokedTokenStatus: revoked.status };
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
    await page.screenshot({ path: path.join(OUT, '05-logout.png'), fullPage: true });

    report.verdict = 'PASS';
  } catch (error) {
    report.error = error instanceof Error ? error.message : String(error);
  } finally {
    token = '';
    validationKey = '';
    if (browser) await browser.close();
    fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  }
  if (report.verdict !== 'PASS') process.exitCode = 1;
})();

const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright-core');

const baseUrl = process.env.DATARA_REBUILD_BASE_URL;
const validationKey = process.env.DATARA_REBUILD_VALIDATION_KEY;
const evidenceDir = path.resolve(__dirname, '../../docs/increments/evidence/R1');
const pagePath = '/rebuild-validation-i1.html';

function shanghaiTimestamp(date) {
  return new Intl.DateTimeFormat('sv-SE', {
    dateStyle: 'short', timeStyle: 'medium', timeZone: 'Asia/Shanghai', hourCycle: 'h23',
  }).format(date);
}

async function waitForCondition(condition, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await condition()) return;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  throw new Error('timed out waiting for the expected visible UI state');
}

async function main() {
  if (!baseUrl || !validationKey) throw new Error('R1 runner requires runtime URL and server-held validation key');
  await fs.mkdir(evidenceDir, { recursive: true });
  const started = new Date();
  const startedAt = started.toISOString();
  const runId = `r1-${startedAt.replace(/[-:.TZ]/g, '').slice(0, 14)}`;
  const checks = [];
  const errors = [];
  const failedRequests = [];
  const expectedNegativeConsole = [];
  const responses = [];
  let browser;

  try {
    const exchange = await fetch(new URL('/api/v1/rebuild/validation-token', baseUrl), {
      method: 'POST',
      headers: { 'X-Backend-Validation-Key': validationKey },
    });
    const exchangeBody = await exchange.json();
    if (!exchange.ok || !exchangeBody?.data?.token) throw new Error(`validation token exchange failed: HTTP ${exchange.status}`);
    const token = exchangeBody.data.token;

    browser = await chromium.launch({ channel: 'chrome', headless: true });
    const context = await browser.newContext();
    await context.addInitScript(value => { window.__DATARA_TEST_TOKEN__ = value; }, token);
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
    page.on('console', message => {
      if (message.type() !== 'error') return;
      const rendered = `console: ${message.text()}`;
      if (/403 \(Forbidden\)|401 \(Unauthorized\)/.test(message.text())) expectedNegativeConsole.push(rendered);
      else errors.push(rendered);
    });
    page.on('response', response => {
      if (response.url().includes('/api/v1/rebuild/')) {
        responses.push({ method: response.request().method(), path: new URL(response.url()).pathname, status: response.status() });
      }
    });
    page.on('requestfailed', request => failedRequests.push({
      method: request.method(), path: new URL(request.url()).pathname,
      error: request.failure()?.errorText || 'request failed',
    }));

    const pageResponse = await page.goto(new URL(pagePath, baseUrl).toString(), { waitUntil: 'domcontentloaded', timeout: 20000 });
    checks.push({ name: 'playwright-r1-page-loaded', pass: Boolean(pageResponse?.ok() && (await page.title()).length > 0), http_status: pageResponse?.status() || null });
    checks.push({ name: 'no-human-login-controls', pass: await page.locator('#username,#password,#login').count() === 0 });
    checks.push({ name: 'runner-token-enabled-controls', pass: await page.locator('#create').isEnabled() && await page.locator('#probe').isEnabled() });

    const projectCountBefore = Number((await page.locator('#projectState').innerText()).match(/\d+/)?.[0] || 0);
    const projectName = `R1 validation ${runId}`;
    await page.locator('#projectName').fill(projectName);
    const createWaiter = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/rebuild/projects');
    await page.locator('#create').click();
    const createResponse = await createWaiter;
    const createBody = await createResponse.json();
    const createdProjectId = createBody?.data?.id ?? null;
    await waitForCondition(async () => (await page.locator('#message').innerText()).includes(projectName));
    await waitForCondition(async () => Number((await page.locator('#projectState').innerText()).match(/\d+/)?.[0] || 0) > projectCountBefore);
    const projectStateText = await page.locator('#projectState').innerText();
    const projectCount = Number(projectStateText.match(/\d+/)?.[0] || 0);
    checks.push({
      name: 'project-created-through-ui',
      pass: createResponse.ok() && Number.isInteger(createdProjectId) && createdProjectId > 0 && projectCount > projectCountBefore,
      http_status: createResponse.status(),
      project_id_type: typeof createdProjectId,
      project_count: projectCount,
      project_state_text: projectStateText,
    });

    const deniedWaiter = page.waitForResponse(response => response.request().method() === 'POST' && /\/members$/.test(new URL(response.url()).pathname));
    await page.locator('#permission').click();
    const deniedResponse = await deniedWaiter;
    await waitForCondition(async () => /403/.test(await page.locator('#message').innerText()));
    checks.push({ name: 'member-write-denied-through-ui', pass: deniedResponse.status() === 403, http_status: deniedResponse.status() });

    const beforeProbe = await page.locator('#capabilities').innerText();
    const probeWaiter = page.waitForResponse(response => response.request().method() === 'POST' && /\/probe$/.test(new URL(response.url()).pathname));
    await page.locator('#probe').click();
    const probeResponse = await probeWaiter;
    const probeBody = await probeResponse.json();
    await waitForCondition(async () => (await page.locator('#capabilities').innerText()) !== beforeProbe);
    const probeVisible = (await page.locator('#capabilities').innerText()).trim().length > 0;
    checks.push({
      name: 'managed-datasource-probe-through-ui',
      pass: probeResponse.ok() && probeVisible && Array.isArray(probeBody?.data?.capabilities) && probeBody.data.capabilities.length > 0,
      http_status: probeResponse.status(),
    });

    const screenshotPath = path.join(evidenceDir, `${runId}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: true });
    const messageBeforeLogout = await page.locator('#message').innerText();
    const logoutWaiter = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/rebuild/logout');
    await page.locator('#logout').click();
    const logoutResponse = await logoutWaiter;
    await waitForCondition(async () => !(await page.locator('#create').isEnabled()) && (await page.locator('#message').innerText()) !== messageBeforeLogout);
    checks.push({ name: 'logout-message-visible', pass: logoutResponse.ok() && (await page.locator('#message').innerText()) !== messageBeforeLogout, http_status: logoutResponse.status() });
    checks.push({ name: 'logout-through-ui', pass: logoutResponse.ok() && !(await page.locator('#create').isEnabled()), http_status: logoutResponse.status() });

    const revoked = await page.evaluate(async () => {
      const response = await fetch('/api/v1/rebuild/projects', {
        headers: { Authorization: `Bearer ${window.__DATARA_TEST_TOKEN__ || ''}` },
      });
      return response.status;
    });
    checks.push({ name: 'revoked-token-denied', pass: revoked === 401, status: revoked });

    const result = {
      run_id: runId,
      started_at: startedAt,
      started_at_local: shanghaiTimestamp(started),
      finished_at: new Date().toISOString(),
      timezone: 'Asia/Shanghai',
      url: new URL(pagePath, baseUrl).toString(),
      browser: `Chrome ${browser.version()}`,
      playwright_validation_url: new URL(pagePath, baseUrl).toString(),
      screenshot: `docs/increments/evidence/R1/${path.basename(screenshotPath)}`,
      created_project_id: createdProjectId,
      actions: ['runner-key exchange (server process only)', 'project form create', 'member permission denial', 'mysql-src profile probe', 'logout', 'revoked token request'],
      checks,
      relevant_responses: responses,
      failed_requests: failedRequests,
      errors,
      expected_negative_console: expectedNegativeConsole,
      outcome: checks.every(item => item.pass) && errors.length === 0 && failedRequests.length === 0 ? 'PASS' : 'FAIL',
    };
    await fs.writeFile(path.join(evidenceDir, `${runId}.json`), `${JSON.stringify(result, null, 2)}\n`, { mode: 0o600 });
    process.stdout.write(`${JSON.stringify({ run_id: runId, outcome: result.outcome, created_project_id: createdProjectId, checks, response_count: responses.length, error_count: errors.length, failed_request_count: failedRequests.length })}\n`);
    if (result.outcome !== 'PASS') process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
  }
}

main().catch(error => {
  process.stderr.write(`R1_PLAYWRIGHT_FAILED: ${error.message}\n`);
  process.exitCode = 1;
});

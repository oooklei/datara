const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright-core');

const baseUrl = process.env.DATARA_REBUILD_BASE_URL;
const validationKey = process.env.DATARA_REBUILD_VALIDATION_KEY;
const expectedBaseUrl = 'http://192.168.1.9:18091';
const evidenceDir = path.resolve(__dirname, '../../docs/increments/evidence/R3');

function check(checks, name, pass, details = {}) {
  checks.push({ name, pass: Boolean(pass), ...details });
  if (!pass) throw new Error(`UI assertion failed: ${name}`);
}

async function main() {
  if (baseUrl !== expectedBaseUrl) throw new Error('S9 runner is restricted to http://192.168.1.9:18091');
  if (!validationKey) throw new Error('S9 runner requires a protected runtime validation key');
  await fs.mkdir(evidenceDir, { recursive: true });

  const startedAt = new Date().toISOString();
  const runId = `R3S9-${startedAt.replace(/[-:.TZ]/g, '').slice(0, 14)}-${crypto.randomBytes(3).toString('hex')}`;
  const pageUrl = new URL('/rebuild-validation-r3-s9.html', baseUrl).toString();
  const checks = [];
  const actions = [];
  const responses = [];
  const errors = [];
  const report = {
    run_id: runId,
    started_at: startedAt,
    timezone: 'Asia/Shanghai',
    url: pageUrl,
    browser: null,
    project_id: null,
    actions,
    checks,
    relevant_responses: responses,
    errors,
    outcome: 'FAIL',
    secrets_recorded: false,
  };

  let browser;
  try {
    const exchange = await fetch(new URL('/api/v1/rebuild/validation-token', baseUrl), {
      method: 'POST',
      headers: { 'X-Backend-Validation-Key': validationKey },
    });
    const exchangeBody = await exchange.json();
    check(checks, 'protected-runner-token-exchange', exchange.ok && Boolean(exchangeBody?.data?.token), {
      http_status: exchange.status,
    });
    const token = exchangeBody.data.token;

    browser = await chromium.launch({ headless: true });
    report.browser = `${browser.browserType().name()} ${browser.version()}`;
    const context = await browser.newContext({ viewport: { width: 1360, height: 720 }, acceptDownloads: false });
    const page = await context.newPage();
    await page.addInitScript(testToken => { window.__DATARA_TEST_TOKEN__ = testToken; }, token);
    page.on('pageerror', error => errors.push({ kind: 'pageerror', message: error.message }));
    page.on('console', message => {
      if (message.type() === 'error') errors.push({ kind: 'console', message: message.text() });
    });
    page.on('requestfailed', request => errors.push({ kind: 'requestfailed', url: request.url(), error: request.failure()?.errorText }));
    page.on('response', response => {
      if (response.url().includes('/legacy/i18/dry-run')) responses.push({ name: 'i18-dry-run', status: response.status() });
      if (response.url().endsWith('/api/v1/rebuild/projects')) responses.push({ name: 'project-list', status: response.status() });
    });

    const loaded = await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    check(checks, 'validation-page-loaded', loaded?.ok(), { http_status: loaded?.status() });
    await page.waitForFunction(() => {
      const select = document.querySelector('#projectSelect');
      return select?.options.length > 0 && Boolean(select.options[0].value);
    }, null, { timeout: 30000 });
    const options = await page.locator('#projectSelect option').evaluateAll(items => items.filter(item => item.value).map(item => ({ id: item.value })));
    check(checks, 'authorized-project-prefilled', options.length > 0 && Boolean(options[0].id), { available_projects: options.length });

    await page.locator('#projectSelect').selectOption(options[0].id);
    report.project_id = Number(options[0].id);
    actions.push({ name: 'select-project-in-page', project_id: report.project_id, at: new Date().toISOString() });
    await page.getByTestId('run-dry-run').click();
    actions.push({ name: 'click-read-only-i18-preview', at: new Date().toISOString() });
    await page.waitForFunction(() => ['预检完成 · 只读', '预检未完成'].includes(document.querySelector('#runtimeStatus')?.textContent), null, { timeout: 120000 });

    const resultStatus = (await page.locator('#runtimeStatus').innerText()).trim();
    const notice = (await page.locator('#notice').innerText()).trim();
    const stats = await page.evaluate(() => ['sourceRows', 'targetRows', 'plannedRows', 'blockedRows'].map(id => document.querySelector(`#${id}`)?.textContent?.trim()));
    check(checks, 'dry-run-api-returned-success', responses.some(item => item.name === 'i18-dry-run' && item.status === 200), {
      status: responses.find(item => item.name === 'i18-dry-run')?.status ?? null,
    });
    check(checks, 'page-rendered-live-dry-run-result', resultStatus === '预检完成 · 只读' && stats.every(value => value && value !== '—'), {
      runtime_status: resultStatus,
      stats_rendered: stats.every(value => value && value !== '—'),
    });
    check(checks, 'page-reported-no-target-import', notice.includes('未执行迁移'));
    check(checks, 'no-browser-errors', errors.length === 0, { error_count: errors.length });

    await page.screenshot({ path: path.join(evidenceDir, `${runId.toLowerCase()}-summary.png`), fullPage: false });
    report.outcome = 'PASS';
    await context.close();
  } catch (error) {
    errors.push({ kind: 'runner', message: error.message });
  } finally {
    if (browser) await browser.close();
    const reportPath = path.join(evidenceDir, `${runId.toLowerCase()}.json`);
    await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    process.stdout.write(`${JSON.stringify({ run_id: runId, outcome: report.outcome, checks, evidence: reportPath })}\n`);
  }

  if (report.outcome !== 'PASS') process.exitCode = 1;
}

main().catch(error => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});

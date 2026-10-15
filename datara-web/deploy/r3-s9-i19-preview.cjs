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
  if (baseUrl !== expectedBaseUrl) throw new Error('I19 runner is restricted to http://192.168.1.9:18091');
  if (!validationKey) throw new Error('I19 runner requires the protected runtime validation key');
  await fs.mkdir(evidenceDir, { recursive: true });
  const startedAt = new Date().toISOString();
  const runId = `R3S9I19-${startedAt.replace(/[-:.TZ]/g, '').slice(0, 14)}-${crypto.randomBytes(3).toString('hex')}`;
  const pageUrl = new URL('/rebuild-validation-r3-s9-i19.html', baseUrl).toString();
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
    source_payload_recorded: false,
    target_writes_authorized: false,
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
    const launchOptions = { headless: true };
    if (process.env.DATARA_PLAYWRIGHT_EXECUTABLE) launchOptions.executablePath = process.env.DATARA_PLAYWRIGHT_EXECUTABLE;
    browser = await chromium.launch(launchOptions);
    report.browser = `${browser.browserType().name()} ${browser.version()}`;
    const context = await browser.newContext({ viewport: { width: 1360, height: 920 } });
    const page = await context.newPage();
    await page.addInitScript(testToken => { window.__DATARA_TEST_TOKEN__ = testToken; }, token);
    page.on('pageerror', error => errors.push({ kind: 'pageerror', message: error.message }));
    page.on('console', message => { if (message.type() === 'error') errors.push({ kind: 'console', message: message.text() }); });
    page.on('requestfailed', request => errors.push({ kind: 'requestfailed', error: request.failure()?.errorText }));
    page.on('response', async response => {
      const url = response.url();
      if (url.endsWith('/api/v1/rebuild/projects')) responses.push({ name: 'project-list', status: response.status() });
      if (url.includes('/legacy/i19/mapping-preview')) {
        const item = { name: 'i19-mapping-preview', status: response.status() };
        try {
          const body = await response.json();
          const data = body?.data || {};
          item.source_schema = data.source?.schema ?? null;
          item.source_counts = data.source?.counts ?? {};
          item.target_counts = data.target?.counts ?? {};
          item.preview_counts = data.preview?.counts ?? {};
          item.parity_verified = data.preview?.parity_verified;
          item.import_enabled = data.preview?.import_enabled;
          item.business_values_absent = !/private_customer_snapshot|internal_only_owner|internal_only_note/.test(JSON.stringify(data));
        } catch { item.body_parse_failed = true; }
        responses.push(item);
      }
    });

    const loaded = await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    check(checks, 'validation-page-loaded', loaded?.ok(), { http_status: loaded?.status() });
    await page.waitForFunction(() => [...document.querySelectorAll('#projectSelect option')].some(option => Boolean(option.value)), null, { timeout: 30000 });
    const projects = await page.locator('#projectSelect option').evaluateAll(options => options.filter(option => option.value).map(option => ({ id: option.value })));
    check(checks, 'authorized-project-prefilled', projects.length > 0, { available_projects: projects.length });
    report.project_id = Number(projects[0].id);
    await page.locator('#projectSelect').selectOption(projects[0].id);
    actions.push({ name: 'select-project-in-page', project_id: report.project_id, at: new Date().toISOString() });
    await page.getByTestId('run-preview').click();
    actions.push({ name: 'click-i19-read-only-mapping-preview', at: new Date().toISOString() });
    await page.getByTestId('runtime-status').getByText('预览完成 · 只读').waitFor({ timeout: 120000 });

    const rendered = await page.evaluate(() => ({
      stats: ['sourceRows', 'newRows', 'matchedRows', 'blockedRows'].map(id => document.querySelector(`#${id}`)?.textContent?.trim()),
      sourceDomains: document.querySelectorAll('#domainRows tr').length,
      previewRows: document.querySelectorAll('#previewRows tr').length,
      issueCodes: [...document.querySelectorAll('#issueList .issue')].map(node => node.textContent?.trim()),
      importControls: [...document.querySelectorAll('button')].filter(button => /导入|迁移|写入/.test(button.innerText)).length,
      warning: document.querySelector('[data-testid="readonly-warning"]')?.innerText || '',
      notice: document.querySelector('#notice')?.innerText || '',
    }));
    const preview = responses.find(item => item.name === 'i19-mapping-preview');
    check(checks, 'i19-preview-api-succeeded', preview?.status === 200, { status: preview?.status ?? null });
    check(checks, 'three-i19-domains-rendered', rendered.sourceDomains === 3, { domain_rows: rendered.sourceDomains, source_counts: preview?.source_counts });
    check(checks, 'counts-and-preview-rendered', rendered.stats.every(value => value && value !== '—') && rendered.previewRows > 0, { stats: rendered.stats, preview_rows: rendered.previewRows });
    check(checks, 'explicit-no-parity-and-no-import', preview?.parity_verified === false && preview?.import_enabled === false, { parity_verified: preview?.parity_verified, import_enabled: preview?.import_enabled });
    check(checks, 'response-contains-no-source-business-values', preview?.business_values_absent === true);
    check(checks, 'read-only-controls-and-boundary-visible', rendered.importControls === 0 && rendered.warning.includes('READ ONLY') && rendered.notice.includes('无导入操作'), { import_controls: rendered.importControls });
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

main().catch(error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });

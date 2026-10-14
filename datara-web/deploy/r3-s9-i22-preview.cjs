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
  if (baseUrl !== expectedBaseUrl) throw new Error('I22 runner is restricted to http://192.168.1.9:18091');
  if (!validationKey) throw new Error('I22 runner requires the protected runtime validation key');
  await fs.mkdir(evidenceDir, { recursive: true });

  const startedAt = new Date().toISOString();
  const runId = `R3S9I22-${startedAt.replace(/[-:.TZ]/g, '').slice(0, 14)}-${crypto.randomBytes(3).toString('hex')}`;
  const pageUrl = new URL('/rebuild-validation-r3-s9-i22.html', baseUrl).toString();
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
    business_payload_recorded: false,
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
    if (process.env.DATARA_PLAYWRIGHT_EXECUTABLE) {
      launchOptions.executablePath = process.env.DATARA_PLAYWRIGHT_EXECUTABLE;
    }
    browser = await chromium.launch(launchOptions);
    report.browser = `${browser.browserType().name()} ${browser.version()}`;
    const context = await browser.newContext({ viewport: { width: 1440, height: 980 }, acceptDownloads: false });
    const page = await context.newPage();
    await page.addInitScript(testToken => { window.__DATARA_TEST_TOKEN__ = testToken; }, token);
    page.on('pageerror', error => errors.push({ kind: 'pageerror', message: error.message }));
    page.on('console', message => {
      if (message.type() === 'error') errors.push({ kind: 'console', message: message.text() });
    });
    page.on('requestfailed', request => errors.push({ kind: 'requestfailed', error: request.failure()?.errorText }));
    page.on('response', async response => {
      const url = response.url();
      if (url.endsWith('/api/v1/rebuild/projects')) {
        responses.push({ name: 'project-list', status: response.status() });
      }
      if (url.includes('/legacy/i22/mapping-preview')) {
        const entry = { name: 'i22-mapping-preview', status: response.status() };
        try {
          const body = await response.json();
          const data = body?.data || {};
          const preview = data.preview || {};
          entry.source_schema = data.source?.schema ?? null;
          entry.source_counts = data.source?.counts ?? {};
          entry.preview_counts = preview.counts ?? {};
          entry.parity_verified = preview.parity_verified;
          entry.import_enabled = preview.import_enabled;
          entry.payload_field_absent = !JSON.stringify(preview).toLowerCase().includes('payload');
        } catch {
          entry.body_parse_failed = true;
        }
        responses.push(entry);
      }
    });

    const loaded = await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    check(checks, 'validation-page-loaded', loaded?.ok(), { http_status: loaded?.status() });
    await page.waitForFunction(() => {
      const select = document.querySelector('#projectSelect');
      return select?.options.length > 0 && [...select.options].some(option => Boolean(option.value));
    }, null, { timeout: 30000 });
    const options = await page.locator('#projectSelect option').evaluateAll(items =>
      items.filter(item => item.value).map(item => ({ id: item.value })),
    );
    check(checks, 'authorized-project-prefilled', options.length > 0 && Boolean(options[0].id), {
      available_projects: options.length,
    });
    report.project_id = Number(options[0].id);
    await page.locator('#projectSelect').selectOption(options[0].id);
    actions.push({ name: 'select-project-in-page', project_id: report.project_id, at: new Date().toISOString() });

    await page.getByTestId('run-preview').click();
    actions.push({ name: 'click-i22-read-only-preview', at: new Date().toISOString() });
    await page.getByTestId('runtime-status').getByText('预览完成 · 只读').waitFor({ timeout: 120000 });

    const summary = await page.evaluate(() => ({
      stats: ['sourceRows', 'newRows', 'matchedRows', 'blockedRows'].map(id =>
        document.querySelector(`#${id}`)?.textContent?.trim(),
      ),
      sourceDomains: document.querySelectorAll('#domainRows tr').length,
      mappedRows: document.querySelectorAll('#previewRows tr').length,
      blockedRows: document.querySelectorAll('#previewRows .blocked').length,
      issueCodes: [...document.querySelectorAll('#issueList .issue strong')].map(item => item.textContent?.trim()),
      importButtons: [...document.querySelectorAll('button')].filter(button => /导入|迁移/.test(button.innerText)).length,
      notice: document.querySelector('#notice')?.innerText || '',
      parityWarning: document.body.innerText.includes('不是内容 parity')
        || document.body.innerText.includes('不代表内容相同'),
    }));
    const previewResponse = responses.find(item => item.name === 'i22-mapping-preview');
    check(checks, 'i22-preview-api-returned-success', previewResponse?.status === 200, {
      status: previewResponse?.status ?? null,
    });
    check(checks, 'source-seven-domains-rendered', summary.sourceDomains === 7, {
      domain_rows: summary.sourceDomains,
      source_counts: previewResponse?.source_counts,
    });
    check(checks, 'mapping-summary-rendered', summary.stats.every(value => value && value !== '—')
      && summary.mappedRows > 0, {
      counts: summary.stats,
      mapped_rows: summary.mappedRows,
    });
    check(checks, 'blocked-row-and-reason-rendered', summary.blockedRows === Number(summary.stats[3])
      && summary.blockedRows > 0 && summary.issueCodes.length > 0, {
      blocked_rows: summary.blockedRows,
      issue_codes: summary.issueCodes,
    });
    check(checks, 'response-explicitly-disables-parity-and-import',
      previewResponse?.parity_verified === false && previewResponse?.import_enabled === false, {
        parity_verified: previewResponse?.parity_verified,
        import_enabled: previewResponse?.import_enabled,
      });
    check(checks, 'payload-not-returned-or-rendered', previewResponse?.payload_field_absent === true, {
      payload_field_absent: previewResponse?.payload_field_absent,
    });
    check(checks, 'page-has-no-import-control-and-explains-identity-only',
      summary.importButtons === 0 && summary.parityWarning && summary.notice.includes('未执行导入'), {
        import_buttons: summary.importButtons,
        identity_only_warning: summary.parityWarning,
      });
    check(checks, 'no-browser-errors', errors.length === 0, { error_count: errors.length });

    await page.screenshot({
      path: path.join(evidenceDir, `${runId.toLowerCase()}-summary.png`),
      fullPage: false,
    });
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

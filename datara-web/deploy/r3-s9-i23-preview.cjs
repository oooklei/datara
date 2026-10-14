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
  if (baseUrl !== expectedBaseUrl) throw new Error('I23 runner is restricted to http://192.168.1.9:18091');
  if (!validationKey) throw new Error('I23 runner requires the protected runtime validation key');
  await fs.mkdir(evidenceDir, { recursive: true });

  const startedAt = new Date().toISOString();
  const runId = `R3S9I23-${startedAt.replace(/[-:.TZ]/g, '').slice(0, 14)}-${crypto.randomBytes(3).toString('hex')}`;
  const pageUrl = new URL('/rebuild-validation-r3-s9-i23.html', baseUrl).toString();
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
    actions,
    checks,
    relevant_responses: responses,
    errors,
    outcome: 'FAIL',
    secrets_recorded: false,
    business_payload_recorded: true,
  };
  let browser;
  try {
    const exchange = await fetch(new URL('/api/v1/rebuild/validation-capabilities/legacy-i23-preview', baseUrl), {
      method: 'POST',
      headers: { 'X-Backend-Validation-Key': validationKey },
    });
    const exchangeBody = await exchange.json();
    const token = exchangeBody?.data?.token;
    check(checks, 'i23-only-capability-issued', exchange.ok && Boolean(token)
      && exchangeBody?.data?.capability === 'legacy:i23:preview'
      && exchangeBody?.data?.expires_in === 900, { http_status: exchange.status, expires_in: exchangeBody?.data?.expires_in ?? null });

    const launchOptions = { headless: true };
    if (process.env.DATARA_PLAYWRIGHT_EXECUTABLE) launchOptions.executablePath = process.env.DATARA_PLAYWRIGHT_EXECUTABLE;
    browser = await chromium.launch(launchOptions);
    report.browser = `${browser.browserType().name()} ${browser.version()}`;
    const context = await browser.newContext({ viewport: { width: 1440, height: 980 }, acceptDownloads: false });
    const page = await context.newPage();
    await page.addInitScript(capability => { window.__DATARA_I23_CAPABILITY__ = capability; }, token);
    page.on('pageerror', error => errors.push({ kind: 'pageerror', message: error.message }));
    page.on('console', message => { if (message.type() === 'error') errors.push({ kind: 'console', message: message.text() }); });
    page.on('requestfailed', request => errors.push({ kind: 'requestfailed', error: request.failure()?.errorText }));
    page.on('response', async response => {
      if (!response.url().includes('/legacy/i23/identity-preview')) return;
      const item = { name: 'i23-identity-preview', status: response.status() };
      try {
        const body = await response.json();
        const data = body?.data || {};
        const preview = data.preview || {};
        item.source_counts = data.source?.counts || {};
        item.target_summary = {
          candidate_users: data.target?.candidate_users ?? 0,
          existing_identity_mappings: data.target?.existing_identity_mappings ?? 0,
        };
        item.preview_counts = preview.counts || {};
        item.issue_codes = [...new Set((preview.issues || []).map(issue => issue.code))].sort();
        item.source_columns = Object.keys(preview.entries?.[0] || {}).filter(key => key.startsWith('source_'));
        item.parity_verified = preview.parity_verified;
        item.import_enabled = preview.import_enabled;
        item.credential_fields_absent = !JSON.stringify(data).toLowerCase().includes('user_pwd')
          && !JSON.stringify(data).toLowerCase().includes('password_hash');
      } catch { item.body_parse_failed = true; }
      responses.push(item);
    });

    const loaded = await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    check(checks, 'i23-validation-page-loaded', loaded?.ok(), { http_status: loaded?.status() });
    await page.getByTestId('runtime-status').getByText('预览完成 · 只读').waitFor({ timeout: 120000 });
    const firstResponse = responses.find(item => item.name === 'i23-identity-preview');
    check(checks, 'i23-preview-api-returned-success', firstResponse?.status === 200, { status: firstResponse?.status ?? null });
    check(checks, 'six-approved-source-fields-rendered', firstResponse?.source_columns?.length === 6, {
      source_column_count: firstResponse?.source_columns?.length ?? 0,
    });
    check(checks, 'credentials-absent-from-preview-response', firstResponse?.credential_fields_absent === true);
    check(checks, 'preview-explicitly-disables-parity-and-import',
      firstResponse?.parity_verified === false && firstResponse?.import_enabled === false);

    const scopedOrdinaryResponse = await fetch(new URL('/api/v1/rebuild/projects', baseUrl), {
      headers: { Authorization: `Bearer ${token}` },
    });
    responses.push({ name: 'scoped-token-ordinary-api-negative-control', status: scopedOrdinaryResponse.status });
    check(checks, 'scoped-token-rejected-by-ordinary-api', scopedOrdinaryResponse.status === 401, {
      http_status: scopedOrdinaryResponse.status,
    });

    const selects = page.locator('select[data-source-id]');
    let candidateSelect = null;
    for (let i = 0; i < await selects.count(); i++) {
      const select = selects.nth(i);
      if (await select.locator('option').count() > 1) {
        candidateSelect = select;
        break;
      }
    }
    if (candidateSelect) {
      await candidateSelect.selectOption({ index: 1 });
      actions.push({ name: 'select-existing-target-user-candidate', at: new Date().toISOString() });
      const nextPreview = page.waitForResponse(response => response.url().includes('/legacy/i23/identity-preview') && response.request().method() === 'POST');
      await page.getByTestId('run-preview').click();
      const response = await nextPreview;
      check(checks, 'explicit-user-selection-preview-rerun', response.status() === 200, { http_status: response.status() });
      await page.getByTestId('runtime-status').getByText('预览完成 · 只读').waitFor({ timeout: 120000 });
    } else {
      await page.getByTestId('run-preview').click();
      actions.push({ name: 'confirm-unresolved-preview-without-candidate', at: new Date().toISOString() });
      await page.getByTestId('runtime-status').getByText('预览完成 · 只读').waitFor({ timeout: 120000 });
    }

    const summary = await page.evaluate(() => ({
      rows: document.querySelectorAll('#rows tr[data-source-id]').length,
      sourceCount: Number(document.querySelector('#sourceCount')?.textContent?.replace(/,/g, '') || 0),
      selections: document.querySelectorAll('#rows select[data-source-id]').length,
      importControls: [...document.querySelectorAll('button')].filter(button => /导入|迁移|创建账号|更新账号/.test(button.innerText)).length,
      warningsVisible: document.body.innerText.includes('不读取密码列')
        && document.body.innerText.includes('没有导入')
        && document.body.innerText.includes('只读边界'),
      pageHasCredentialInput: Boolean(document.querySelector('input[type="password"]')),
    }));
    check(checks, 'identity-records-and-selection-controls-rendered', summary.rows === summary.sourceCount
      && summary.selections === summary.rows, {
      source_rows: summary.rows,
      source_count: summary.sourceCount,
      selection_controls: summary.selections,
    });
    check(checks, 'no-account-mutation-or-import-control', summary.importControls === 0 && !summary.pageHasCredentialInput, summary);
    check(checks, 'readonly-policy-visible', summary.warningsVisible);
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

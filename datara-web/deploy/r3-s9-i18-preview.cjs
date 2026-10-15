const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright-core');

const baseUrl = process.env.DATARA_REBUILD_BASE_URL;
const validationKey = process.env.DATARA_REBUILD_VALIDATION_KEY;
const adminToken = process.env.DATARA_REBUILD_ADMIN_TOKEN;
const expectedBaseUrl = 'http://192.168.1.9:18091';
const evidenceDir = path.resolve(__dirname, '../../docs/increments/evidence/R3');

function check(checks, name, pass, details = {}) {
  checks.push({ name, pass: Boolean(pass), ...details });
  if (!pass) throw new Error(`UI assertion failed: ${name}`);
}

async function main() {
  if (baseUrl !== expectedBaseUrl) throw new Error('S9 runner is restricted to http://192.168.1.9:18091');
  if (!validationKey && !adminToken) throw new Error('S9 runner requires a protected runtime validation key or a manually injected short-lived admin token');
  if (validationKey && adminToken) throw new Error('Set exactly one of DATARA_REBUILD_VALIDATION_KEY / DATARA_REBUILD_ADMIN_TOKEN');
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
    auth_mode: adminToken ? 'admin-headed-manual-injection' : 'protected-runner-token-exchange',
    project_id: null,
    snapshot_digests: null,
    actions,
    checks,
    relevant_responses: responses,
    errors,
    outcome: 'FAIL',
    secrets_recorded: false,
  };

  let browser;
  try {
    let token;
    let adminHeaded = false;
    if (adminToken) {
      // #2 人工确认闸路径：短时 admin token 由人工经 headed launcher（SecureString）注入本进程，
      // 仅经 addInitScript 进入当前页面内存；不进 URL/DOM 属性/持久存储/日志/证据/仓库。
      adminHeaded = true;
      token = adminToken;
      check(checks, 'admin-token-manual-injection-mode', token.trim().length > 0);
    } else {
      const exchange = await fetch(new URL('/api/v1/rebuild/validation-token', baseUrl), {
        method: 'POST',
        headers: { 'X-Backend-Validation-Key': validationKey },
      });
      const exchangeBody = await exchange.json();
      check(checks, 'protected-runner-token-exchange', exchange.ok && Boolean(exchangeBody?.data?.token), {
        http_status: exchange.status,
      });
      token = exchangeBody.data.token;
    }

    const launchOptions = { headless: adminHeaded ? false : true };
    if (process.env.DATARA_PLAYWRIGHT_EXECUTABLE) {
      launchOptions.executablePath = process.env.DATARA_PLAYWRIGHT_EXECUTABLE;
    }
    browser = await chromium.launch(launchOptions);
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
      if (response.url().includes('/legacy/i18/import')) responses.push({ name: 'i18-import', status: response.status() });
      if (response.url().endsWith('/api/v1/rebuild/projects')) responses.push({ name: 'project-list', status: response.status() });
    });

    const loaded = await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    check(checks, 'validation-page-loaded', loaded?.ok(), { http_status: loaded?.status() });
    await page.waitForFunction(() => {
      const select = document.querySelector('#projectSelect');
      return select?.options.length > 0 && Boolean(select.options[0].value);
    }, null, { timeout: 30000 });
    const options = await page.locator('#projectSelect option').evaluateAll(items => items.filter(item => item.value).map(item => ({ id: item.value })));
    const approvedProject = options.find(project => project.id === '3');
    check(checks, 'approved-project-3', Boolean(approvedProject), { available_projects: options.length });

    await page.locator('#projectSelect').selectOption(approvedProject.id);
    report.project_id = Number(approvedProject.id);
    actions.push({ name: 'select-project-in-page', project_id: report.project_id, at: new Date().toISOString() });
    await page.getByTestId('run-dry-run').click();
    actions.push({ name: 'click-read-only-i18-preview', at: new Date().toISOString() });
    await page.waitForFunction(() => ['complete', 'failed'].includes(document.querySelector('#runtimeStatus')?.dataset.state), null, { timeout: 120000 });

    const resultStatus = await page.locator('#runtimeStatus').getAttribute('data-state');
    const notice = (await page.locator('#notice').innerText()).trim();
    const stats = await page.evaluate(() => ['sourceRows', 'targetRows', 'plannedRows', 'skippedRows', 'blockedRows'].map(id => document.querySelector(`#${id}`)?.textContent?.trim()));
    const snapshotDigests = await page.evaluate(() => ({
      source_digest: document.querySelector('#sourceDigest')?.textContent?.trim() || '',
      target_digest: document.querySelector('#targetDigest')?.textContent?.trim() || '',
    }));
    report.snapshot_digests = snapshotDigests;
    check(checks, 'approved-i18-snapshot-digests', /^[0-9a-f]{64}$/.test(snapshotDigests.source_digest) && /^[0-9a-f]{64}$/.test(snapshotDigests.target_digest), {
      source_digest: snapshotDigests.source_digest,
      target_digest: snapshotDigests.target_digest,
    });
    const visibleIssues = await page.locator('#issueList .issue').allTextContents();
    const planRows = await page.locator('#planRows tr').allTextContents();
    const issueCodeCounts = visibleIssues.reduce((counts, text) => {
      const code = text.trim().split(/\s+/)[0] || 'unclassified';
      counts[code] = (counts[code] || 0) + 1;
      return counts;
    }, {});
    check(checks, 'dry-run-api-returned-success', responses.some(item => item.name === 'i18-dry-run' && item.status === 200), {
      status: responses.find(item => item.name === 'i18-dry-run')?.status ?? null,
      failure_notice: responses.some(item => item.name === 'i18-dry-run' && item.status >= 400) ? notice : undefined,
    });
    check(checks, 'page-rendered-live-dry-run-result', resultStatus === 'complete' && stats.every(value => value && value !== '—'), {
      runtime_status: resultStatus,
      stats_rendered: stats.every(value => value && value !== '—'),
      rendered_counts: stats,
      visible_issue_count: visibleIssues.length,
      issue_code_counts: issueCodeCounts,
      issue_samples: visibleIssues.slice(0, 12),
    });
    check(checks, 'approved-orphan-version-is-visible-as-skipped', Number(stats[3]) === 1 && planRows.some(row => row.includes('t_dw_model_version') && row.includes('skipped') && row.includes('approved_missing_model_reference')), {
      skipped_count: stats[3],
      matching_rows: planRows.filter(row => row.includes('t_dw_model_version')),
    });
    check(checks, 'approved-relation-field-mappings-are-visible', planRows.some(row => row.includes('order_id') && row.includes('order_no')) && planRows.some(row => row.includes('dt') && row.includes('order_date')), {
      mapping_rows: planRows.filter(row => row.includes('order_id') || row.includes('order_date')),
    });
    check(checks, 'page-reported-no-target-import', notice.includes('未执行迁移'));
    const confirmationPhrase = await page.getByTestId('required-confirm-phrase').innerText();
    const confirmationEnabled = await page.locator('#importConfirmPhrase').isEnabled();
    const importButtonDisabled = await page.locator('#runI18Import').isDisabled();
    check(
      checks,
      'run-i18-import-confirmation-ready',
      resultStatus === 'complete' && confirmationEnabled && importButtonDisabled &&
        confirmationPhrase === `IMPORT I18 3 ${snapshotDigests.source_digest} ${snapshotDigests.target_digest}`,
      {
        confirmation_input_enabled: confirmationEnabled,
        import_button_disabled_until_human_confirmation: importButtonDisabled,
        confirmation_phrase_matches_live_digests: confirmationPhrase ===
          `IMPORT I18 3 ${snapshotDigests.source_digest} ${snapshotDigests.target_digest}`,
      },
    );
    check(checks, 'no-browser-errors', errors.length === 0, { error_count: errors.length });

    if (adminHeaded) {
      // 人工确认闸：headed 窗口交由人工输入确认语并点击导入；runner 不代输、不点击（任何模式）。
      // 仅等待页面自身在导入完成后展示批次结果，并记录导入响应状态作为证据。
      check(checks, 'import-gate-open-for-human', await page.locator('#runI18Import').isEnabled());
      actions.push({ name: 'waiting-for-human-confirmation-and-click', at: new Date().toISOString() });
      await page.waitForFunction(
        () => /批次/.test(document.querySelector('#importStatus')?.textContent || ''),
        null,
        { timeout: 600000 },
      );
      const importStatusText = (await page.locator('#importStatus').innerText()).trim();
      const importResponse = responses.find(item => item.name === 'i18-import');
      check(checks, 'human-confirmed-import-recorded', Boolean(importResponse) && /批次/.test(importStatusText), {
        import_http_status: importResponse?.status ?? null,
        import_completed: /导入与只读复核通过|导入事务已完成/.test(importStatusText),
      });
      actions.push({ name: 'human-confirmation-finished', at: new Date().toISOString() });
    }

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

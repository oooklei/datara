const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright-core');

const baseUrl = process.env.DATARA_REBUILD_BASE_URL;
const validationKey = process.env.DATARA_REBUILD_VALIDATION_KEY;
const expectedBaseUrl = 'http://192.168.1.9:18091';
const evidenceDir = path.resolve(__dirname, '../../docs/increments/evidence/R3');

function requireCheck(checks, name, condition, details = {}) {
  checks.push({ name, pass: Boolean(condition), ...details });
  if (!condition) throw new Error(`UI assertion failed: ${name}`);
}

async function submitForm(page) {
  await page.locator('#submitModal').click();
  await page.locator('#modalBackdrop').waitFor({ state: 'hidden', timeout: 15000 });
  return (await page.locator('#notice').innerText()).trim();
}

async function fillAndSubmit(page, fields) {
  for (const [name, value] of Object.entries(fields)) await page.locator(`#field-${name}`).fill(value);
  return submitForm(page);
}

async function main() {
  if (!baseUrl || !validationKey) throw new Error('R3 runner requires the protected runtime URL and validation key');
  if (baseUrl !== expectedBaseUrl) throw new Error('R3 runner is restricted to the approved validation origin');

  await fs.mkdir(evidenceDir, { recursive: true });
  const startedAt = new Date().toISOString();
  const stamp = startedAt.replace(/[-:.TZ]/g, '').slice(0, 14);
  const runId = `R3V-${stamp}-${crypto.randomBytes(3).toString('hex')}`;
  const slug = runId.toLowerCase().replace(/[^a-z0-9]+/g, '_');
  const pageUrl = new URL('/rebuild-validation-r3.html', baseUrl).toString();
  const checks = [];
  const actions = [];
  const responses = [];
  const errors = [];
  let browser;
  let page;
  let expectedConflictWindow = false;
  let expectedRetiredQc404Window = false;
  let projectId;
  let projectName;

  const result = {
    run_id: runId,
    started_at: startedAt,
    timezone: 'Asia/Shanghai',
    url: pageUrl,
    browser: null,
    fixture: { project_name: null, project_id: null },
    actions,
    checks,
    relevant_responses: responses,
    errors,
    outcome: 'FAIL',
    secrets_recorded: false,
  };

  try {
    const exchange = await fetch(new URL('/api/v1/rebuild/validation-token', baseUrl), {
      method: 'POST',
      headers: { 'X-Backend-Validation-Key': validationKey },
    });
    const exchangeBody = await exchange.json();
    if (!exchange.ok || !exchangeBody?.data?.token) throw new Error(`validation-token exchange failed: HTTP ${exchange.status}`);
    const token = exchangeBody.data.token;
    requireCheck(checks, 'protected-runner-token-exchange', exchange.ok && Boolean(token), { http_status: exchange.status });

    const existingProjectId = Number(process.env.DATARA_R3_PROJECT_ID || 0);
    if (existingProjectId > 0) {
      const projectsResponse = await fetch(new URL('/api/v1/rebuild/projects', baseUrl), {
        headers: { Authorization: `Bearer ${token}` },
      });
      const projectsBody = await projectsResponse.json();
      const project = projectsBody?.data?.list?.find(item => item.id === existingProjectId);
      if (!projectsResponse.ok || !project || !project.name.startsWith('R3 governance validation ')) {
        throw new Error('requested resume project is not an owned R3 validation fixture');
      }
      projectId = project.id;
      projectName = project.name;
      result.fixture = { project_name: projectName, project_id: projectId, http_status: projectsResponse.status, reused: true };
      actions.push({ name: 'reuse-isolated-validation-project', at: new Date().toISOString(), project_id: projectId, http_status: projectsResponse.status });
    } else {
      projectName = `R3 governance validation ${runId}`;
      const projectResponse = await fetch(new URL('/api/v1/rebuild/projects', baseUrl), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: projectName, description: `Isolated R3 governance UI validation ${runId}` }),
      });
      const projectBody = await projectResponse.json();
      if (!projectResponse.ok || !projectBody?.data?.id) throw new Error(`isolated project fixture creation failed: HTTP ${projectResponse.status}`);
      projectId = projectBody.data.id;
      result.fixture = { project_name: projectName, project_id: projectId, http_status: projectResponse.status, setup_only: true };
      actions.push({ name: 'prepare-isolated-validation-project', at: new Date().toISOString(), project_id: projectId, http_status: projectResponse.status });
    }

    browser = await chromium.launch({ channel: 'chrome', headless: true });
    result.browser = `Chrome ${browser.version()}`;
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    await context.addInitScript(value => { window.__DATARA_TEST_TOKEN__ = value; }, token);
    page = await context.newPage();
    page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
    page.on('console', message => {
      const expectedConflict = expectedConflictWindow && /409 \(Conflict\)/.test(message.text());
      const expectedQcNotFound = expectedRetiredQc404Window && /404 \(Not Found\)/.test(message.text());
      if (message.type() === 'error' && !expectedConflict && !expectedQcNotFound) errors.push(`console: ${message.text()}`);
    });
    page.on('requestfailed', request => errors.push(`requestfailed: ${request.method()} ${new URL(request.url()).pathname} ${request.failure()?.errorText || ''}`));
    page.on('response', async response => {
      const request = response.request();
      const url = new URL(response.url());
      if (!url.pathname.startsWith('/api/v1/rebuild/')) return;
      const entry = { at: new Date().toISOString(), method: request.method(), path: url.pathname, status: response.status() };
      if (request.method() === 'POST' && response.ok()) {
        try {
          const body = await response.json();
          if (body?.data?.id != null) entry.record_id = body.data.id;
        } catch { /* Only statuses and generated IDs are retained. */ }
      }
      responses.push(entry);
    });

    const landing = await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.locator('#projectSelect:not(:disabled)').waitFor({ state: 'visible', timeout: 15000 });
    await page.locator('#apiState').getByText('后端已连接').waitFor({ state: 'visible', timeout: 15000 });
    requireCheck(checks, 'governance-page-loaded', Boolean(landing?.ok()), { http_status: landing?.status() || null });
    requireCheck(checks, 'no-human-login-or-token-storage', await page.locator('#username,#password,#login').count() === 0 && !(await page.locator('body').innerText()).includes('X-Backend-Validation-Key'));
    requireCheck(checks, 'project-selector-loaded-from-backend', (await page.locator('#projectSelect option').count()) > 0);
    expectedRetiredQc404Window = true;
    const retiredQcStatus = await page.evaluate(async () => (await fetch('/api/v1/qc/rules')).status);
    expectedRetiredQc404Window = false;
    requireCheck(checks, 'legacy-quality-api-retired', retiredQcStatus === 404, { http_status: retiredQcStatus });
    actions.push({ name: 'confirm-legacy-qc-api-is-not-mounted', at: new Date().toISOString(), http_status: retiredQcStatus });
    await page.locator('#projectSelect').selectOption(String(projectId));
    await page.locator('#addAsset:not(:disabled)').waitFor({ state: 'visible', timeout: 10000 });
    actions.push({ name: 'select-isolated-project', at: new Date().toISOString(), project_id: projectId });

    const sourceName = `${slug}_orders_src`;
    const targetName = `${slug}_orders_dw`;
    await page.locator('#addAsset').click();
    const sourceNotice = await fillAndSubmit(page, {
      asset_name: sourceName,
      display_name: `${runId} source orders`,
      domain_name: 'r3-validation',
    });
    const sourceId = Number(sourceNotice.match(/记录 ID\s*(\d+)/)?.[1]);
    requireCheck(checks, 'create-source-asset-through-form', sourceId > 0, { rendered_notice: sourceNotice });
    actions.push({ name: 'create-source-asset', at: new Date().toISOString(), asset_id: sourceId });

    await page.locator('#addAsset').click();
    const targetNotice = await fillAndSubmit(page, {
      asset_name: targetName,
      display_name: `${runId} curated orders`,
      domain_name: 'r3-validation',
    });
    const targetId = Number(targetNotice.match(/记录 ID\s*(\d+)/)?.[1]);
    requireCheck(checks, 'create-target-asset-through-form', targetId > 0 && targetId !== sourceId, { rendered_notice: targetNotice });
    actions.push({ name: 'create-target-asset', at: new Date().toISOString(), asset_id: targetId });

    await page.locator('#assetSchema').click();
    await page.getByText('order_id', { exact: true }).waitFor({ state: 'visible', timeout: 10000 });
    requireCheck(checks, 'asset-schema-tab-renders-persisted-fields', (await page.locator('#tabContent').innerText()).includes('created_at'));
    await page.locator('#assetOverview').click();

    await page.locator('#addTag').click();
    const tagKey = `${slug}_tag`;
    const tagNotice = await fillAndSubmit(page, {
      tag_key: tagKey,
      display_name: `${runId} sales tag`,
    });
    requireCheck(checks, 'create-and-attach-tag-through-form', /已保存/.test(tagNotice), { rendered_notice: tagNotice });
    actions.push({ name: 'create-and-attach-tag', at: new Date().toISOString() });

    await page.locator('#assetSearch').fill(sourceName);
    await page.locator(`[data-asset-id="${sourceId}"]`).waitFor({ state: 'visible', timeout: 10000 });
    requireCheck(checks, 'catalog-search-filters-real-asset', await page.locator('#assetRows').innerText().then(text => text.includes(sourceName)));
    await page.locator('#assetSearch').fill('');
    await page.locator('#applyFilters').click();
    await page.locator(`[data-asset-id="${sourceId}"]`).waitFor({ state: 'visible', timeout: 10000 });
    await page.locator(`[data-asset-id="${sourceId}"]`).click();

    await page.locator('#addRule').click();
    const ruleName = `${slug}_order_id_not_null`;
    const ruleNotice = await fillAndSubmit(page, { name: ruleName, expression: 'order_id IS NOT NULL' });
    requireCheck(checks, 'create-quality-rule-definition-through-form', /已保存/.test(ruleNotice), { rendered_notice: ruleNotice });
    await page.locator('#assetQuality').click();
    await page.getByText(ruleName, { exact: false }).waitFor({ state: 'visible', timeout: 10000 });
    await page.getByText('尚无真实运行记录', { exact: false }).waitFor({ state: 'visible', timeout: 10000 });
    const qualityText = await page.locator('#tabContent').innerText();
    requireCheck(checks, 'quality-history-is-real-empty-state-not-fabricated', qualityText.includes('尚无真实运行记录'), { rendered_text: qualityText });
    actions.push({ name: 'define-quality-rule-and-check-history', at: new Date().toISOString() });

    await page.locator('#assetLineage').click();
    await page.locator('#createLineage').waitFor({ state: 'visible', timeout: 10000 });
    await page.locator('#createLineage').click();
    const externalId = `${slug}_lineage_${sourceId}_${targetId}`;
    await page.locator('#field-external_id').fill(externalId);
    await page.locator('#field-source_asset_id').selectOption(String(sourceId));
    await page.locator('#field-target_asset_id').selectOption(String(targetId));
    const lineageNotice = await submitForm(page);
    requireCheck(checks, 'create-field-lineage-through-form', /已保存/.test(lineageNotice), { rendered_notice: lineageNotice });
    await page.getByText(/1 条边/).waitFor({ state: 'visible', timeout: 10000 });
    const lineageText = await page.locator('#tabContent').innerText();
    requireCheck(checks, 'lineage-graph-renders-persisted-edge', lineageText.includes('1 条边'), { rendered_text: lineageText });
    actions.push({ name: 'create-and-traverse-lineage', at: new Date().toISOString() });

    const standardCode = `R3_${runId.replace(/[^A-Z0-9]/g, '_')}_ID`;
    await page.locator('#addStandard').click();
    const standardNotice = await fillAndSubmit(page, { code: standardCode, name: `${runId} order identifier` });
    requireCheck(checks, 'create-standard-through-form', /已保存/.test(standardNotice), { rendered_notice: standardNotice });
    actions.push({ name: 'create-standard', at: new Date().toISOString() });

    await page.locator('#addMetric').click();
    const metricCode = `R3_${runId.replace(/[^A-Z0-9]/g, '_')}_COUNT`;
    const metricNotice = await fillAndSubmit(page, { code: metricCode, name: `${runId} order count` });
    requireCheck(checks, 'create-semantic-metric-through-form', /已保存/.test(metricNotice), { rendered_notice: metricNotice });
    actions.push({ name: 'create-semantic-metric', at: new Date().toISOString() });

    await page.locator('#addStandard').click();
    await page.locator('#field-code').fill(standardCode);
    await page.locator('#field-name').fill(`${runId} duplicate standard`);
    expectedConflictWindow = true;
    const expectedConflict = page.waitForResponse(response => {
      const request = response.request();
      return request.method() === 'POST' && new URL(response.url()).pathname === `/api/v1/rebuild/governance/projects/${projectId}/standards` && response.status() === 409;
    }, { timeout: 10000 });
    await page.locator('#submitModal').click();
    const conflictResponse = await expectedConflict;
    await page.getByText(/失败（HTTP 409）/).waitFor({ state: 'visible', timeout: 10000 });
    requireCheck(checks, 'duplicate-standard-conflict-shown-as-real-409', (await page.locator('#notice').innerText()).includes('409'));
    requireCheck(checks, 'duplicate-standard-conflict-is-backend-409', conflictResponse.status() === 409, { http_status: conflictResponse.status() });
    expectedConflictWindow = false;
    await page.locator('#cancelModal').click();
    actions.push({ name: 'duplicate-standard-negative-control', at: new Date().toISOString(), expected_http_status: 409 });

    await page.locator('#assetAudit').click();
    await page.getByText('asset.create', { exact: true }).first().waitFor({ state: 'visible', timeout: 10000 });
    const auditText = await page.locator('#tabContent').innerText();
    requireCheck(checks, 'audit-tab-renders-persisted-events', auditText.includes('asset.create') && auditText.includes('lineage.create'), { rendered_text: auditText });
    requireCheck(checks, 'audit-renders-generated-time', /20\d\d-\d\d-\d\d/.test(auditText));
    await page.screenshot({ path: path.join(evidenceDir, `${runId}-governance.png`), fullPage: true });
    actions.push({ name: 'inspect-activity-audit', at: new Date().toISOString() });

    await page.locator('#logout').click();
    await page.getByText('验证会话已撤销', { exact: false }).waitFor({ state: 'visible', timeout: 10000 });
    const revokedResponse = await fetch(new URL('/api/v1/rebuild/projects', baseUrl), { headers: { Authorization: `Bearer ${token}` } });
    requireCheck(checks, 'page-logout-revokes-runner-token', revokedResponse.status === 401, { http_status: revokedResponse.status });
    actions.push({ name: 'logout-and-confirm-token-revocation', at: new Date().toISOString() });
    result.record_ids = { source_asset_id: sourceId, target_asset_id: targetId, project_id: projectId };
    result.canonical_codes = { standard: standardCode, metric: metricCode, tag: tagKey, rule: ruleName, lineage: externalId };
    result.outcome = errors.length === 0 && checks.every(item => item.pass) ? 'PASS' : 'FAIL';
  } catch (error) {
    errors.push(`${error.name}: ${error.message}`);
    result.outcome = 'FAIL';
  } finally {
    if (page) {
      try { await page.screenshot({ path: path.join(evidenceDir, `${runId}-final.png`), fullPage: true }); } catch { /* Preserve primary failure. */ }
    }
    if (browser) await browser.close();
    result.finished_at = new Date().toISOString();
    result.fixture.project_name = projectName;
    result.fixture.project_id = projectId || null;
    const evidencePath = path.join(evidenceDir, `${runId}-playwright.json`);
    await fs.writeFile(evidencePath, `${JSON.stringify(result, null, 2)}\n`, { mode: 0o600 });
    process.stdout.write(`${JSON.stringify({ run_id: runId, outcome: result.outcome, checks, response_count: responses.length, error_count: errors.length, evidence: path.basename(evidencePath) })}\n`);
  }
  if (result.outcome !== 'PASS') process.exitCode = 1;
}

main().catch(error => {
  process.stderr.write(`R3_PLAYWRIGHT_FAILED: ${error.message}\n`);
  process.exitCode = 1;
});

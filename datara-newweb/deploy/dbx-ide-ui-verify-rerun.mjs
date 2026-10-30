/**
 * datara 宿主 × dbx IDE 集成 UI 验收 —— 重跑（P0-1 / P1-2 / P2-4 修复后）。
 *
 * 与首轮 `dbx-ide-ui-verify.mjs` 的差异：
 *   1) 先验证裸 `/ide`（无尾斜杠）301 是否返回相对 Location（P2-4）；
 *   2) 同时在**宿主帧与 dbx iframe 帧**注入 message 监听，直接证明 iframe 收到 `datara:variables`；
 *   3) 用真实常量查询 `SELECT '${global.biz_date}' AS dt` 验证「直执行成功且不弹参数弹窗」；
 *   4) 点击 `data-variable-refresh` 验证重新拉取 + 重新下发；
 *   5) 追加敏感变量脱敏渲染验证（项目 33 无 sensitive 变量，用路由 mock 覆盖前端渲染路径，明确标注）。
 *
 * 用法（token 只经环境变量注入，绝不落盘/入库/入 URL）：
 *   $env:DATARA_TEST_TOKEN = <短时 token>
 *   node deploy/dbx-ide-ui-verify-rerun.mjs --base http://192.168.1.9:18091 --out ./.evidence/dbx-ide
 */
import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

function parseArgs(argv) {
  const args = {
    base: 'http://192.168.1.9:18091',
    out: '.evidence/dbx-ide',
    headless: 'true',
    path: '/p/33/ide',
    project: '33',
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    if (key.startsWith('--')) {
      const name = key.slice(2);
      const value = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : 'true';
      args[name] = value;
    }
  }
  return args;
}

const args = parseArgs(process.argv);
const token = process.env.DATARA_TEST_TOKEN || '';
const base = args.base.replace(/\/+$/, '');
const outDir = path.resolve(args.out);
const result = {
  base,
  startedAt: new Date().toISOString(),
  tokenInjected: Boolean(token),
  steps: {},
  consoleErrors: [],
  pageErrors: [],
  apiCalls: [],
  badResponses: [],
  dbxQueryCalls: [],
  screenshots: [],
};

async function maskVariablePanel(page) {
  // 截图期间临时打码并保存原文，截完还原，避免污染后续断言读取。
  await page.evaluate(() => {
    const saved = [];
    document.querySelectorAll('[data-variable-value],[data-variable-masked]').forEach((el) => {
      saved.push([el, el.textContent]);
      el.textContent = '******';
    });
    globalThis.__MASK_SAVED__ = saved;
  });
}

async function restoreVariablePanel(page) {
  await page
    .evaluate(() => {
      const saved = globalThis.__MASK_SAVED__ ?? [];
      saved.forEach(([el, text]) => {
        el.textContent = text;
      });
      globalThis.__MASK_SAVED__ = [];
    })
    .catch(() => {});
}

async function shot(page, name) {
  await maskVariablePanel(page);
  const file = path.join(outDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  result.screenshots.push(path.relative(process.cwd(), file));
  await restoreVariablePanel(page);
}

/** 读取宿主帧消息日志。 */
async function hostLog(page) {
  return page.evaluate(() => globalThis.__DBX_MSG_LOG__ ?? []).catch(() => []);
}

function isDbxFrame(f) {
  try {
    const p = new URL(f.url()).pathname;
    return p === '/ide/' || p === '/ide';
  } catch {
    return false;
  }
}

/** 读取 dbx iframe 帧消息日志（证明 iframe 侧确实收到 datara:variables）。 */
async function frameLog(page) {
  const frame = page.frames().find(isDbxFrame);
  if (!frame) return { frameUrl: null, log: [] };
  const log = await frame.evaluate(() => globalThis.__DBX_MSG_LOG__ ?? []).catch(() => []);
  return { frameUrl: frame.url(), log };
}

async function probeDialog(page) {
  return page.evaluate(() => {
    const doc = document.querySelector('#dbx-ide-frame')?.contentDocument;
    if (!doc) return { accessible: false };
    const vis = (el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const cands = [
      ...doc.querySelectorAll('[role="dialog"], [class*="modal"], [class*="dialog"], [data-state="open"]'),
    ]
      .filter(vis)
      .slice(0, 5)
      .map((el) => ({
        cls: (el.getAttribute('class') ?? '').slice(0, 100),
        text: (el.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 300),
      }));
    const bodyText = (doc.body?.innerText ?? '').replace(/\s+/g, ' ').trim();
    return {
      dialogCount: cands.length,
      dialogs: cands,
      mentionsParameter: /SQL 参数|参数名|Parameter/.test(bodyText),
      mentionsBizDate: bodyText.includes('2026-10-28'),
      bodyTextHead: bodyText.slice(0, 500),
    };
  });
}

async function main() {
  await fs.mkdir(outDir, { recursive: true });
  if (!token) throw new Error('DATARA_TEST_TOKEN 未设置（token 只经环境变量注入）');

  const browser = await chromium.launch({
    headless: args.headless !== 'false',
    args: ['--no-proxy-server', '--proxy-bypass-list=*'],
  });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });

  await context.addInitScript((value) => {
    globalThis.__DATARA_TEST_TOKEN__ = value;
  }, token);

  // 宿主帧 + iframe 帧都会执行本脚本：分别记录各自收到的 datara:* 消息。
  await context.addInitScript(() => {
    globalThis.__DBX_MSG_LOG__ = [];
    window.addEventListener('message', (event) => {
      const data = event.data;
      if (!data || typeof data !== 'object') return;
      if (typeof data.type !== 'string' || !data.type.startsWith('datara:')) return;
      globalThis.__DBX_MSG_LOG__.push({
        type: data.type,
        count: typeof data.count === 'number' ? data.count : undefined,
        entries: Array.isArray(data.entries)
          ? data.entries.map((x) => ({
              scope: x.scope,
              name: x.name,
              sensitive: x.sensitive === true,
              value: typeof x.value === 'string' ? x.value : x.value,
            }))
          : undefined,
        frameUrl: location.href,
        isTop: window === window.top,
        at: Date.now(),
      });
    });
  });

  // ---- 步骤 0：裸 /ide（无尾斜杠）301 是否保留端口（P2-4） ----
  const bare = await context.request.get(`${base}/ide`, { maxRedirects: 0, timeout: 15000 });
  const bareFollow = await context.request.get(`${base}/ide`, { maxRedirects: 5, timeout: 20000 });
  result.steps.bareIdeRedirect = {
    status: bare.status(),
    location: bare.headers()['location'] ?? null,
    locationIsRelative: (bare.headers()['location'] ?? '').startsWith('/'),
    followedStatus: bareFollow.status(),
    followedUrl: bareFollow.url(),
  };

  const page = await context.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error') result.consoleErrors.push(msg.text().slice(0, 300));
  });
  page.on('pageerror', (err) => result.pageErrors.push(String(err).slice(0, 300)));
  page.on('request', (req) => {
    const url = req.url();
    if (url.includes('/api/v1/')) result.apiCalls.push({ method: req.method(), url: url.replace(base, '') });
    if (url.includes('/ide/api/')) result.dbxQueryCalls.push({ method: req.method(), url: url.replace(base, ''), at: Date.now() });
  });
  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/v1/')) {
      const hit = result.apiCalls.find((c) => c.url === url.replace(base, '') && c.status === undefined);
      if (hit) hit.status = res.status();
    }
    if (res.status() >= 400) result.badResponses.push({ status: res.status(), url: url.replace(base, '') });
  });

  // ---- 步骤 1/2：宿主页 + iframe ----
  const response = await page.goto(`${base}${args.path}`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  result.steps.goto = { status: response?.status() ?? 0, requestedPath: args.path, finalPath: new URL(page.url()).pathname };
  await page.waitForSelector('#dbx-ide-frame', { state: 'attached', timeout: 30000 });

  result.steps.hostHeader = await page.evaluate(() => {
    const btn = (sel) => {
      const el = document.querySelector(sel);
      return el ? { present: true, text: (el.textContent || '').trim(), disabled: el.disabled === true } : { present: false };
    };
    return {
      contextText: (document.querySelector('[data-dbx-context]')?.textContent || '').replace(/\s+/g, ' ').trim(),
      project: (document.querySelector('[data-dbx-project]')?.textContent || '').trim(),
      environment: (document.querySelector('[data-dbx-environment]')?.textContent || '').trim(),
      envInput: Boolean(document.querySelector('input[data-environment-group]')),
      refresh: btn('[data-variable-refresh]'),
      manage: btn('[data-variable-manage]'),
      iframeSrc: document.querySelector('#dbx-ide-frame')?.getAttribute('src') ?? null,
    };
  });

  // 等 iframe 文档就绪
  let iframeTitle = '';
  for (let i = 0; i < 60; i += 1) {
    iframeTitle = await page
      .evaluate(() => document.querySelector('#dbx-ide-frame')?.contentDocument?.title ?? '')
      .catch(() => '');
    if (iframeTitle) break;
    await page.waitForTimeout(500);
  }
  result.steps.iframeDocument = await page.evaluate(() => {
    const doc = document.querySelector('#dbx-ide-frame')?.contentDocument;
    if (!doc) return { accessible: false };
    const scripts = [...doc.querySelectorAll('script[src]')].map((s) => s.getAttribute('src')).slice(0, 6);
    const assets = performance
      .getEntriesByType('resource')
      .map((e) => e.name)
      .filter((n) => n.includes('/ide/assets/'));
    return {
      accessible: true,
      title: doc.title,
      url: doc.location?.href ?? '',
      readyState: doc.readyState,
      scripts,
      assetCount: assets.length,
      assetSample: assets.slice(0, 3),
      counts: {
        codemirror: doc.querySelectorAll('.cm-editor').length,
        buttons: doc.querySelectorAll('button').length,
      },
    };
  });

  // ---- 步骤 3：变量现值面板 ----
  await page.waitForSelector('[data-variable-panel]', { state: 'attached', timeout: 20000 });
  result.steps.variablePanelReady = await page
    .waitForFunction(
      () => {
        const panelEl = document.querySelector('[data-variable-panel]');
        if (!panelEl) return false;
        if (panelEl.querySelector('[data-variable-empty]')) return false;
        return panelEl.querySelectorAll('[data-variable-row]').length > 0;
      },
      { timeout: 20000 },
    )
    .then(() => true)
    .catch(() => false);

  const readPanel = () =>
    page.evaluate(() => {
      const panelEl = document.querySelector('[data-variable-panel]');
      if (!panelEl) return { present: false };
      const rows = [...panelEl.querySelectorAll('[data-variable-row]')].map((row) => ({
        name: row.querySelector('.dbx-var-name')?.textContent?.trim() ?? '',
        type: row.querySelector('.dbx-var-type')?.textContent?.trim() ?? '',
        value: row.querySelector('[data-variable-value]')?.textContent?.trim() ?? null,
        masked: row.querySelector('[data-variable-masked]')?.textContent?.trim() ?? null,
        isMasked: Boolean(row.querySelector('[data-variable-masked]')),
      }));
      return {
        present: true,
        empty: Boolean(panelEl.querySelector('[data-variable-empty]')),
        header: panelEl.querySelector('.dbx-var-head')?.textContent?.replace(/\s+/g, ' ').trim() ?? '',
        rowCount: rows.length,
        maskedCount: rows.filter((r) => r.isMasked).length,
        rows,
      };
    });
  result.steps.variablePanel = await readPanel();
  await shot(page, 'r2-01-host-ide-variable-panel');

  // ---- 步骤 4：变量自动下发（bridge-ready → 宿主补发 → dbx 收 → ack） ----
  let host = [];
  let frameSide = { frameUrl: null, log: [] };
  for (let i = 0; i < 60; i += 1) {
    host = await hostLog(page);
    frameSide = await frameLog(page);
    const gotAck = host.some((m) => m.type === 'datara:variables-ack');
    const gotVars = frameSide.log.some((m) => m.type === 'datara:variables');
    if (gotAck && gotVars) break;
    await page.waitForTimeout(250);
  }
  const ack = host.filter((m) => m.type === 'datara:variables-ack');
  const varsAtFrame = frameSide.log.filter((m) => m.type === 'datara:variables');
  result.steps.variableBridge = {
    bridgeReadyCount: host.filter((m) => m.type === 'datara:bridge-ready').length,
    ackCount: ack.length,
    ackPayloadCount: ack.at(-1)?.count ?? null,
    frameUrl: frameSide.frameUrl,
    frameReceivedVariablesCount: varsAtFrame.length,
    frameReceivedEntries: varsAtFrame.at(-1)?.entries ?? null,
    frameSawAck: frameSide.log.some((m) => m.type === 'datara:variables-ack'),
    hostLogTypes: host.map((m) => m.type),
    dataCloneError: result.consoleErrors.filter((t) => /DataCloneError|could not be cloned/i.test(t)),
  };
  await shot(page, 'r2-02-after-variable-bridge');

  // ---- 步骤 5：SQL 变量直执行（成功且不弹参数弹窗） ----
  const sqlProbe = { sql: "SELECT '${global.biz_date}' AS dt" };
  const queryCallsBefore = result.dbxQueryCalls.length;
  try {
    const frameLoc = page.frameLocator('#dbx-ide-frame');
    const newQueryBtn = frameLoc.locator('button:has-text("新建查询")');
    try {
      await newQueryBtn.first().waitFor({ state: 'visible', timeout: 30000 });
    } catch {
      /* 落到下方 count 判定 */
    }
    sqlProbe.newQueryCount = await newQueryBtn.count();
    if (sqlProbe.newQueryCount === 0) {
      sqlProbe.note = '未找到「新建查询」按钮';
    } else {
      await newQueryBtn.first().click();
      await page.waitForTimeout(3000);
      const editor = frameLoc.locator('.cm-content');
      sqlProbe.editorCount = await editor.count();
      if (sqlProbe.editorCount > 0) {
        await editor.first().click({ timeout: 5000 });
        await page.keyboard.press('Control+A');
        await page.keyboard.type(sqlProbe.sql, { delay: 5 });
        await page.waitForTimeout(800);
        sqlProbe.enteredText = await page.evaluate(
          () => (document.querySelector('#dbx-ide-frame')?.contentDocument?.querySelector('.cm-content')?.textContent ?? '').slice(0, 200),
        );
        await shot(page, 'r2-03-sql-entered');

        // 优先快捷键 Ctrl+Enter；未触发请求再回落工具栏按钮。
        await page.keyboard.press('Control+Enter');
        let fired = false;
        for (let i = 0; i < 24; i += 1) {
          if (result.dbxQueryCalls.length > queryCallsBefore) {
            fired = true;
            break;
          }
          await page.waitForTimeout(250);
        }
        sqlProbe.trigger = fired ? 'keyboard:Control+Enter' : null;

        if (!fired) {
          const clicked = await page.evaluate(() => {
            const doc = document.querySelector('#dbx-ide-frame')?.contentDocument;
            if (!doc) return null;
            const vis = (el) => {
              const r = el.getBoundingClientRect();
              return r.width > 0 && r.height > 0;
            };
            const btns = [...doc.querySelectorAll('button')].filter(vis);
            const named = btns.find((b) =>
              /执行|运行|Run|Execute/i.test(
                `${b.getAttribute('title') ?? ''} ${b.getAttribute('aria-label') ?? ''} ${b.textContent ?? ''}`,
              ),
            );
            if (named) {
              const r = named.getBoundingClientRect();
              return {
                by: 'title/aria/text',
                label: (named.getAttribute('title') || named.getAttribute('aria-label') || named.textContent || '').trim(),
                x: r.left + r.width / 2,
                y: r.top + r.height / 2,
              };
            }
            const cand = btns
              .map((b) => {
                const r = b.getBoundingClientRect();
                return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height };
              })
              .filter((o) => o.y >= 60 && o.y <= 110 && o.w <= 34 && o.h <= 34)
              .sort((a, b) => a.x - b.x);
            if (!cand.length) return null;
            return { by: 'toolbar-coordinate', x: cand[0].x, y: cand[0].y, candidates: cand.length };
          });
          if (clicked) {
            const hostRect = await page.evaluate(() => {
              const r = document.querySelector('#dbx-ide-frame')?.getBoundingClientRect();
              return r ? { left: r.left, top: r.top } : null;
            });
            await page.mouse.click(hostRect.left + clicked.x, hostRect.top + clicked.y);
            sqlProbe.trigger = `click:${clicked.by}`;
            sqlProbe.runButton = clicked;
            for (let i = 0; i < 24; i += 1) {
              if (result.dbxQueryCalls.length > queryCallsBefore) break;
              await page.waitForTimeout(250);
            }
          } else {
            sqlProbe.note = (sqlProbe.note ? `${sqlProbe.note}；` : '') + '未找到执行按钮';
          }
        }

        await page.waitForTimeout(4000);
        sqlProbe.newQueryCalls = result.dbxQueryCalls.slice(queryCallsBefore);
        sqlProbe.dialog = await probeDialog(page);
        sqlProbe.resultShowsValue = sqlProbe.dialog?.mentionsBizDate ?? false;
        await shot(page, 'r2-04-sql-after-run');
      } else {
        sqlProbe.note = '编辑器打开后未找到 CodeMirror .cm-content';
      }
    }
  } catch (e) {
    sqlProbe.error = String(e && e.stack ? e.stack : e).slice(0, 800);
  }
  result.steps.sqlDirectRun = sqlProbe;

  // ---- 步骤 6：刷新按钮重新拉取并重新下发 ----
  const beforeRefresh = {
    completeCalls: result.apiCalls.filter((c) => c.url.includes('/rebuild/variables/complete')).length,
    ackCount: (await hostLog(page)).filter((m) => m.type === 'datara:variables-ack').length,
    frameVars: (await frameLog(page)).log.filter((m) => m.type === 'datara:variables').length,
  };
  await page.click('[data-variable-refresh]');
  let refreshObserved = false;
  for (let i = 0; i < 60; i += 1) {
    const afterAck = (await hostLog(page)).filter((m) => m.type === 'datara:variables-ack').length;
    const afterVars = (await frameLog(page)).log.filter((m) => m.type === 'datara:variables').length;
    const afterComplete = result.apiCalls.filter((c) => c.url.includes('/rebuild/variables/complete')).length;
    if (afterAck > beforeRefresh.ackCount && afterVars > beforeRefresh.frameVars && afterComplete > beforeRefresh.completeCalls) {
      refreshObserved = true;
      break;
    }
    await page.waitForTimeout(250);
  }
  result.steps.refresh = {
    before: beforeRefresh,
    after: {
      completeCalls: result.apiCalls.filter((c) => c.url.includes('/rebuild/variables/complete')).length,
      ackCount: (await hostLog(page)).filter((m) => m.type === 'datara:variables-ack').length,
      frameVars: (await frameLog(page)).log.filter((m) => m.type === 'datara:variables').length,
    },
    rePulledAndResent: refreshObserved,
    panelAfter: await readPanel(),
  };
  await shot(page, 'r2-05-after-refresh');

  // ---- 步骤 7（补充）：敏感变量脱敏渲染路径（项目 33 无 sensitive 变量 → 路由 mock） ----
  const mockPage = await context.newPage();
  const SECRET = 'real-secret-should-not-leak';
  await mockPage.route('**/api/v1/rebuild/variables/complete', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'success',
        data: [
          { scope: 'project', name: 'dw_name', value_type: 'string', current_value: 'datara_dw', sensitive: false },
          { scope: 'project', name: 'api_secret', value_type: 'string', current_value: SECRET, sensitive: true },
        ],
      }),
    });
  });
  await mockPage.goto(`${base}${args.path}`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await mockPage.waitForSelector('[data-variable-panel]', { state: 'attached', timeout: 20000 });
  await mockPage
    .waitForFunction(() => document.querySelectorAll('[data-variable-row]').length > 0, { timeout: 20000 })
    .catch(() => {});
  await mockPage.waitForTimeout(2500);
  const mockPanel = await mockPage.evaluate(() => {
    const rows = [...document.querySelectorAll('[data-variable-row]')].map((row) => ({
      name: row.querySelector('.dbx-var-name')?.textContent?.trim() ?? '',
      value: row.querySelector('[data-variable-value]')?.textContent?.trim() ?? null,
      masked: row.querySelector('[data-variable-masked]')?.textContent?.trim() ?? null,
      isMasked: Boolean(row.querySelector('[data-variable-masked]')),
    }));
    return { rows, bodyContainsSecret: document.body.innerText.includes('real-secret-should-not-leak') };
  });
  const mockFrame = mockPage.frames().find(isDbxFrame);
  const mockFrameLog = mockFrame ? await mockFrame.evaluate(() => globalThis.__DBX_MSG_LOG__ ?? []).catch(() => []) : [];
  const mockVars = mockFrameLog.filter((m) => m.type === 'datara:variables').at(-1)?.entries ?? null;
  result.steps.sensitiveMasking = {
    mode: 'route-mock（项目 33 无真实 sensitive 变量，仅覆盖前端渲染与下发脱敏路径）',
    panel: mockPanel,
    frameEntries: mockVars,
    frameEntryValueIsMasked: Array.isArray(mockVars)
      ? mockVars.find((e) => e.name === 'api_secret')?.value === '***'
      : null,
    framePayloadContainsSecret: JSON.stringify(mockVars ?? []).includes(SECRET),
  };
  await shot(mockPage, 'r2-06-sensitive-masked');

  result.finishedAt = new Date().toISOString();
  await browser.close();
  await fs.writeFile(path.join(outDir, 'last-run-rerun.json'), JSON.stringify(result, null, 2), 'utf8');
  console.log(JSON.stringify(result, null, 2));
}

main().catch(async (err) => {
  result.fatal = String(err && err.stack ? err.stack : err).slice(0, 1200);
  try {
    await fs.mkdir(outDir, { recursive: true });
    await fs.writeFile(path.join(outDir, 'last-run-rerun.json'), JSON.stringify(result, null, 2), 'utf8');
  } catch {
    /* ignore */
  }
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = 1;
});

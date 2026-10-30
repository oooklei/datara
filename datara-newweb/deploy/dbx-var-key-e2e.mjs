/**
 * dbx 侧变量键口径端到端验证（直连 dbx 容器 4224，不经 datara 宿主）。
 *
 * 目的：判定 datara 下发 {scope,name} 与 dbx `lookupExternalVariable` 的 `${scope}.${name}` 口径是否一致。
 * 方法：向 dbx 窗口 postMessage 注入与 datara 同形载荷（scope=global, name=biz_date），
 *       在 SQL 编辑器输入 `SELECT * FROM t WHERE dt = '${global.biz_date}'` 并执行，
 *       断言：① 无原生参数弹窗；② execute-multi 请求体中变量已被替换为字面值。
 *
 * 用法：node deploy/dbx-var-key-e2e.mjs --base http://127.0.0.1:4224 --out ./.evidence/dbx-var-key
 */
import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

function parseArgs(argv) {
  const args = { base: 'http://127.0.0.1:4224', out: '.evidence/dbx-var-key', headless: 'true' };
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
const base = args.base.replace(/\/+$/, '');
const origin = base;
const outDir = path.resolve(args.out);
const result = {
  base,
  origin,
  startedAt: new Date().toISOString(),
  steps: {},
  messages: [],
  executeRequests: [],
  consoleErrors: [],
  pageErrors: [],
};

async function main() {
  await fs.mkdir(outDir, { recursive: true });
  // 本机系统代理不可用，直连 192.168.1.9 / 127.0.0.1 必须绕过代理。
  const browser = await chromium.launch({
    headless: args.headless !== 'false',
    args: ['--no-proxy-server', '--proxy-bypass-list=*'],
  });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });

  // 捕获 dbx 回发的 datara:* 消息（含 variables-ack）。
  await context.addInitScript(() => {
    globalThis.__DBX_MSG_LOG__ = [];
    window.addEventListener('message', (event) => {
      const data = event.data;
      if (data && typeof data === 'object' && typeof data.type === 'string' && data.type.startsWith('datara:')) {
        globalThis.__DBX_MSG_LOG__.push({ type: data.type, count: data.count, origin: event.origin, at: Date.now() });
      }
    });
  });

  const page = await context.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error') result.consoleErrors.push(msg.text().slice(0, 200));
  });
  page.on('pageerror', (err) => result.pageErrors.push(String(err).slice(0, 200)));
  page.on('request', (req) => {
    if (req.url().includes('/ide/api/query/execute-multi')) {
      result.executeRequests.push({ method: req.method(), url: req.url(), postData: req.postData() ?? null });
    }
  });

  // ---- 1. 打开 dbx 直连入口 ----
  const response = await page.goto(`${base}/ide/`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  result.steps.goto = { status: response?.status() ?? 0, finalUrl: page.url() };

  const newQueryBtn = page.locator('button:has-text("新建查询")');
  try {
    await newQueryBtn.first().waitFor({ state: 'visible', timeout: 40000 });
  } catch {
    /* 落到下方 count 判定 */
  }
  result.steps.newQueryButton = (await newQueryBtn.count()) > 0;

  // ---- 2. 注入与 datara 同形的变量载荷（scope=global, name=biz_date） ----
  const payload = [
    { scope: 'global', name: 'biz_date', valueType: 'date', value: '2026-10-28', sensitive: false },
  ];
  result.steps.injectedPayload = payload;
  await page.evaluate(
    (entries) => window.postMessage({ type: 'datara:variables', entries }, '*'),
    payload,
  );
  for (let i = 0; i < 40; i += 1) {
    result.messages = await page.evaluate(() => globalThis.__DBX_MSG_LOG__ ?? []);
    if (result.messages.some((m) => m.type === 'datara:variables-ack')) break;
    await page.waitForTimeout(250);
  }
  result.steps.ack = result.messages.find((m) => m.type === 'datara:variables-ack') ?? null;

  // ---- 3. 打开编辑器并输入含变量的 SQL ----
  await newQueryBtn.first().click();
  await page.waitForTimeout(2500);
  const editor = page.locator('.cm-content');
  if ((await editor.count()) === 0) {
    result.steps.editor = { found: false };
    console.log(JSON.stringify(result, null, 2));
    await browser.close();
    return;
  }
  await editor.first().click({ timeout: 5000 });
  await page.keyboard.press('Control+A');
  await page.keyboard.type("SELECT * FROM t WHERE dt = '${global.biz_date}'", { delay: 4 });
  await page.waitForTimeout(800);
  result.steps.sql = await page.evaluate(() => (document.querySelector('.cm-content')?.textContent ?? '').slice(0, 200));

  // ---- 4. 执行：优先 Ctrl+Enter，回退工具栏图标坐标 ----
  await page.keyboard.press('Control+Enter');
  await page.waitForTimeout(1500);
  if (result.executeRequests.length === 0) {
    const clickPt = await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button')];
      const cand = btns
        .map((b) => {
          const r = b.getBoundingClientRect();
          return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height };
        })
        .filter((o) => o.w > 0 && o.h > 0 && o.y >= 60 && o.y <= 110 && o.x >= 240 && o.x <= 560 && o.w <= 32 && o.h <= 32)
        .sort((a, b) => a.x - b.x);
      return cand[0] ?? null;
    });
    if (clickPt) {
      await page.mouse.click(clickPt.x, clickPt.y);
      result.steps.runBy = 'toolbar-coordinate';
    }
    await page.waitForTimeout(3500);
  } else {
    result.steps.runBy = 'ctrl-enter';
  }

  // ---- 5. 判定：参数弹窗 + 请求体替换结果 ----
  result.steps.dialog = await page.evaluate(() => {
    const vis = (el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const cands = [...document.querySelectorAll('[role="dialog"], [class*="modal"], [data-state="open"]')].filter(vis);
    const bodyText = (document.body?.innerText ?? '').replace(/\s+/g, ' ').trim();
    return {
      dialogCount: cands.length,
      dialogTexts: cands.map((el) => (el.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 200)),
      mentionsParameter: /参数|Parameter/.test(bodyText),
    };
  });

  // 请求体替换断言
  const body = result.executeRequests[0]?.postData ?? '';
  result.steps.requestBody = body.slice(0, 600);
  result.steps.substitution = {
    requestSent: result.executeRequests.length > 0,
    containsLiteral: body.includes('2026-10-28'),
    containsPlaceholder: body.includes('global.biz_date'),
  };

  await page.screenshot({ path: path.join(outDir, 'after-run.png') });
  result.finishedAt = new Date().toISOString();
  await browser.close();
  console.log(JSON.stringify(result, null, 2));
}

main().catch(async (err) => {
  result.fatal = String(err && err.stack ? err.stack : err).slice(0, 1200);
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = 1;
});

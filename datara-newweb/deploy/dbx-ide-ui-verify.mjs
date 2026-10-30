/**
 * datara 宿主 × dbx IDE iframe 集成 UI 验证（Playwright）。
 *
 * 用法（token 只经环境变量注入，绝不落盘/入库/入 URL）：
 *   $env:DATARA_TEST_TOKEN = <短时 token>
 *   node deploy/dbx-ide-ui-verify.mjs --base http://192.168.1.9:18093 --out ./.evidence/dbx-ide
 *
 * 步骤：
 *   1) 注入 token 后打开 <base>/ide（守卫会重定向到 /p/<activeId>/ide）
 *   2) 校验 #dbx-ide-frame 出现、src 含 /ide/、iframe 文档 title 为 DBX
 *   3) 校验变量现值面板 data-variable-panel / data-variable-row / 敏感脱敏
 *   4) 校验变量下发：宿主侧监听 message，捕获 datara:variables-ack
 *   5) 校验 SQL 变量直执行：iframe 内输入 SELECT ... '${global.biz_date}' 并触发执行，
 *      判定是否弹出原生参数弹窗（未弹出 + 发起请求 = 直执行命中）
 *
 * 产出：JSON 结果（stdout）+ 截图（自动对变量面板值打码）。
 */
import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

function parseArgs(argv) {
  // 注意：nginx `location /ide/` 前缀匹配会让裸 `/ide` 触发 301，且 absolute_redirect 默认
  // 用 $host（不含端口）→ Location 丢端口（http://192.168.1.9/ide/）。因此入口用项目作用域
  // 路由 /p/<activeId>/ide（走 location / → SPA），由 DbxIdeView 承载 iframe。
  const args = { base: 'http://192.168.1.9:18093', out: '.evidence/dbx-ide', headless: 'true', path: '/p/33/ide' };
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
  messages: [],
  screenshots: [],
};

async function maskVariablePanel(page) {
  // 截图前对变量值文本打码（普通变量值虽非秘密，也统一遮蔽避免误泄）。
  await page.evaluate(() => {
    document.querySelectorAll('[data-variable-value],[data-variable-masked]').forEach((el) => {
      el.textContent = '******';
    });
  });
}

async function shot(page, name) {
  await maskVariablePanel(page);
  const file = path.join(outDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  result.screenshots.push(path.relative(process.cwd(), file));
}

async function main() {
  await fs.mkdir(outDir, { recursive: true });
  if (!token) throw new Error('DATARA_TEST_TOKEN 未设置（token 只经环境变量注入）');

  // 本机系统代理（127.0.0.1:7993）不可用，直连 192.168.1.9 必须绕过代理。
  const browser = await chromium.launch({
    headless: args.headless !== 'false',
    args: ['--no-proxy-server', '--proxy-bypass-list=*'],
  });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  await context.addInitScript((value) => {
    globalThis.__DATARA_TEST_TOKEN__ = value;
  }, token);
  const page = await context.newPage();

  page.on('console', (msg) => {
    if (msg.type() === 'error') result.consoleErrors.push(msg.text().slice(0, 300));
  });
  page.on('pageerror', (err) => result.pageErrors.push(String(err).slice(0, 300)));
  page.on('request', (req) => {
    const url = req.url();
    if (url.includes('/api/v1/')) result.apiCalls.push({ method: req.method(), url: url.replace(base, '') });
  });
  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/v1/')) {
      const hit = result.apiCalls.find((c) => c.url === url.replace(base, '') && c.status === undefined);
      if (hit) hit.status = res.status();
    }
    if (res.status() >= 400) {
      result.badResponses.push({ status: res.status(), url: url.replace(base, '') });
    }
  });

  // 宿主侧消息监听（datara:variables / datara:variables-ack / datara:bridge-ready）
  await page.addInitScript(() => {
    globalThis.__DBX_MSG_LOG__ = [];
    window.addEventListener('message', (event) => {
      const data = event.data;
      if (!data || typeof data !== 'object') return;
      if (typeof data.type === 'string' && data.type.startsWith('datara:')) {
        globalThis.__DBX_MSG_LOG__.push({
          type: data.type,
          count: typeof data.count === 'number' ? data.count : undefined,
          entries: Array.isArray(data.entries) ? data.entries.length : undefined,
          origin: event.origin,
          at: Date.now(),
        });
      }
    });
  });

  // ---- 步骤 1/2：打开 /ide，校验 iframe ----
  const response = await page.goto(`${base}${args.path}`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  result.steps.goto = { status: response?.status() ?? 0, requestedPath: args.path, finalPath: new URL(page.url()).pathname };
  await page.waitForSelector('#dbx-ide-frame', { state: 'attached', timeout: 30000 });
  const frameHandle = await page.$('#dbx-ide-frame');
  const frameEl = await frameHandle.evaluate((el) => ({ src: el.getAttribute('src'), id: el.id }));
  result.steps.iframeElement = frameEl;

  const frame = page.frames().find((f) => f.url().includes('/ide/')) ?? null;
  result.steps.iframeFrame = frame ? { url: frame.url() } : null;

  // 等待 iframe 文档就绪
  let iframeTitle = '';
  for (let i = 0; i < 60; i += 1) {
    iframeTitle = await page
      .evaluate(() => {
        const el = document.querySelector('#dbx-ide-frame');
        return el?.contentDocument?.title ?? '';
      })
      .catch(() => '');
    if (iframeTitle) break;
    await page.waitForTimeout(500);
  }
  const iframeInfo = await page.evaluate(() => {
    const el = document.querySelector('#dbx-ide-frame');
    const doc = el?.contentDocument;
    if (!doc) return { accessible: false };
    const bodyText = (doc.body?.innerText ?? '').replace(/\s+/g, ' ').trim();
    return {
      accessible: true,
      title: doc.title,
      url: doc.location?.href ?? '',
      readyState: doc.readyState,
      bodyTextHead: bodyText.slice(0, 300),
      hasStartupLoading: Boolean(doc.querySelector('#startup-loading')),
      counts: {
        monaco: doc.querySelectorAll('.monaco-editor').length,
        codemirror: doc.querySelectorAll('.cm-editor').length,
        textarea: doc.querySelectorAll('textarea').length,
        tabs: doc.querySelectorAll('[role="tab"]').length,
        buttons: doc.querySelectorAll('button').length,
      },
    };
  });
  result.steps.iframeDocument = iframeInfo;

  // ---- 步骤 3：变量现值面板 ----
  // 面板先渲染空态，变量加载完成后空态消失；必须等空态消失再断言，避免竞态读到 0 行。
  await page.waitForSelector('[data-variable-panel]', { state: 'attached', timeout: 20000 });
  result.steps.variablePanelReady = await page
    .waitForFunction(() => {
      const panelEl = document.querySelector('[data-variable-panel]');
      if (!panelEl) return false;
      if (panelEl.querySelector('[data-variable-empty]')) return false;
      return panelEl.querySelectorAll('[data-variable-row]').length > 0;
    }, { timeout: 20000 })
    .then(() => true)
    .catch(() => false);
  const panel = await page.evaluate(() => {
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
      emptyText: panelEl.querySelector('[data-variable-empty]')?.textContent?.trim() ?? '',
      header: panelEl.querySelector('.dbx-var-head')?.textContent?.replace(/\s+/g, ' ').trim() ?? '',
      rowCount: rows.length,
      rows,
    };
  });
  result.steps.variablePanel = panel;
  await shot(page, '01-host-ide-variable-panel');

  // ---- 步骤 4：变量下发 ack ----
  let messages = [];
  for (let i = 0; i < 40; i += 1) {
    messages = await page.evaluate(() => globalThis.__DBX_MSG_LOG__ ?? []);
    if (messages.some((m) => m.type === 'datara:variables-ack')) break;
    await page.waitForTimeout(250);
  }
  result.messages = messages;
  result.steps.variableBridge = {
    bridgeReady: messages.some((m) => m.type === 'datara:bridge-ready'),
    ack: messages.find((m) => m.type === 'datara:variables-ack') ?? null,
    ackCount: messages.filter((m) => m.type === 'datara:variables-ack').length,
  };

  // ---- 步骤 4b：桥接诊断（定位 DataCloneError 根因：普通对象 vs Proxy 载荷） ----
  const bridgeDiag = await page.evaluate(async () => {
    const el = document.querySelector('#dbx-ide-frame');
    const w = el && el.contentWindow;
    if (!w) return { ok: false, reason: 'iframe contentWindow 不可用' };
    const out = { ok: true };
    const seen = [];
    const onMsg = (e) => {
      if (e.data && typeof e.data === 'object') seen.push({ type: e.data.type, count: e.data.count });
    };
    w.addEventListener('message', onMsg);
    const plain = [
      { scope: 'global', name: 'biz_date', valueType: 'date', value: '2026-10-28', sensitive: false },
    ];
    try {
      w.postMessage({ type: 'datara:variables', entries: plain }, window.location.origin);
      out.plainPayload = 'sent';
    } catch (e) {
      out.plainPayload = `threw: ${String(e).slice(0, 200)}`;
    }
    try {
      w.postMessage(
        { type: 'datara:variables', entries: new Proxy(plain.slice(), {}) },
        window.location.origin,
      );
      out.proxyPayload = 'sent';
    } catch (e) {
      out.proxyPayload = `threw: ${String(e).slice(0, 220)}`;
    }
    await new Promise((r) => setTimeout(r, 1500));
    out.iframeSeen = seen;
    w.removeEventListener('message', onMsg);
    return out;
  });
  result.steps.bridgeDiagnostic = bridgeDiag;
  result.messages = await page.evaluate(() => globalThis.__DBX_MSG_LOG__ ?? []);
  result.steps.variableBridge.ackAfterManualPlainPayload = result.messages.filter(
    (m) => m.type === 'datara:variables-ack',
  );

  // ---- 步骤 5：SQL 变量直执行（打开编辑器 → 输入 → 执行 → 判定是否回落参数弹窗） ----
  async function probeSql(page, shotName) {
    const sql = { attempted: false, editorOpened: false, sqlEntered: false, executed: false };
    try {
      const frameLoc = page.frameLocator('#dbx-ide-frame');
      const newQueryBtn = frameLoc.locator('button:has-text("新建查询")');
      // dbx 前端异步启动，重载后需等待「新建查询」可见，避免竞态读不到按钮。
      try {
        await newQueryBtn.first().waitFor({ state: 'visible', timeout: 30000 });
      } catch {
        /* 落到下方 count 判定 */
      }
      if ((await newQueryBtn.count()) === 0) {
        sql.note = '未找到「新建查询」按钮，无法打开编辑器';
        return sql;
      }
      await newQueryBtn.first().click();
      sql.attempted = true;
      await page.waitForTimeout(3000);
      sql.editorOpened = true;
      sql.editorDump = await page.evaluate(() => {
        const doc = document.querySelector('#dbx-ide-frame')?.contentDocument;
        if (!doc) return { accessible: false };
        const vis = (el) => {
          const r = el.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        };
        return {
          accessible: true,
          monaco: doc.querySelectorAll('.monaco-editor').length,
          monacoInputarea: doc.querySelectorAll('.monaco-editor textarea.inputarea').length,
          cm: doc.querySelectorAll('.cm-editor').length,
          textareas: doc.querySelectorAll('textarea').length,
          tabs: [...doc.querySelectorAll('[role="tab"]')].filter(vis).map((t) => (t.textContent || '').trim()).slice(0, 20),
          buttons: [...doc.querySelectorAll('button')]
            .filter(vis)
            .map((b) => (b.textContent || '').trim() || b.getAttribute('aria-label') || b.getAttribute('title') || '')
            .filter(Boolean)
            .slice(0, 40),
        };
      });

      // dbx 编辑器为 CodeMirror 6（.cm-editor / .cm-content，contenteditable=true）。
      const editor = frameLoc.locator('.cm-content');
      if ((await editor.count()) > 0) {
        await editor.first().click({ timeout: 5000 });
        await page.keyboard.press('Control+A');
        await page.keyboard.type("SELECT * FROM t WHERE dt = '${global.biz_date}'", { delay: 4 });
        await page.waitForTimeout(1000);
        sql.sqlEntered = true;
        sql.cmText = await page.evaluate(() => {
          const doc = document.querySelector('#dbx-ide-frame')?.contentDocument;
          return (doc?.querySelector('.cm-content')?.textContent ?? '').slice(0, 200);
        });
      } else {
        sql.note = '编辑器打开后未找到 CodeMirror .cm-content';
      }
      await shot(page, shotName);

      // 执行按钮为工具栏无文本图标按钮（实测 x≈272,y≈82，24x24，无 aria/title）。
      // 按坐标点击编辑器工具栏第一个可见图标按钮（y 70-95，x 250-500，尺寸 ≤32）。
      const clickPt = await page.evaluate(() => {
        const doc = document.querySelector('#dbx-ide-frame')?.contentDocument;
        if (!doc) return null;
        const btns = [...doc.querySelectorAll('button')];
        const cand = btns
          .map((b) => {
            const r = b.getBoundingClientRect();
            return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height };
          })
          .filter((o) => o.w > 0 && o.h > 0 && o.y >= 70 && o.y <= 95 && o.x >= 250 && o.x <= 500 && o.w <= 32 && o.h <= 32)
          .sort((a, b2) => a.x - b2.x);
        const hostRect = document.querySelector('#dbx-ide-frame')?.getBoundingClientRect();
        const target = cand[0];
        if (!target || !hostRect) return null;
        return { x: hostRect.left + target.x, y: hostRect.top + target.y, candidates: cand.length };
      });
      if (clickPt && clickPt.candidates > 0) {
        await page.mouse.click(clickPt.x, clickPt.y);
        sql.executed = true;
        sql.runButton = { by: 'toolbar-coordinate', ...clickPt };
        await page.waitForTimeout(3500);
        // 执行后截图（捕获参数弹窗等回落证据）。
        await shot(page, `${shotName}-after-run`);
      } else {
        sql.note = (sql.note ? sql.note + '；' : '') + '未找到执行按钮（工具栏图标按钮）';
      }

      sql.dialogProbe = await page.evaluate(() => {
        const doc = document.querySelector('#dbx-ide-frame')?.contentDocument;
        if (!doc) return { accessible: false };
        const vis = (el) => {
          const r = el.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        };
        const cands = [...doc.querySelectorAll('[role="dialog"], [class*="modal"], [class*="dialog"], [data-state="open"]')]
          .filter(vis)
          .slice(0, 5)
          .map((el) => ({
            cls: (el.getAttribute('class') ?? '').slice(0, 100),
            text: (el.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 300),
          }));
        const bodyText = (doc.body?.innerText ?? '').replace(/\s+/g, ' ').trim();
        const mentionsParameter = /参数|Parameter/.test(bodyText);
        return { dialogCount: cands.length, dialogs: cands, mentionsParameter, bodyTextHead: bodyText.slice(0, 400) };
      });
    } catch (e) {
      sql.error = String(e && e.stack ? e.stack : e).slice(0, 800);
    }
    return sql;
  }

  // 步骤 5：dbx 已被步骤 4b 的手动 plain 载荷灌入 biz_date 快照（用于验证 dbx 侧替换逻辑本身）。
  result.steps.sqlProbe = await probeSql(page, '02-dbx-editor');

  // ---- 步骤 5b：干净状态复测（不注入任何手动载荷，模拟真实用户路径）----
  // 步骤 4b 的手动 plain 载荷会把 biz_date 灌入 dbx 快照，掩盖「宿主自动下发失败」的后果。
  // 重新加载页面以清空 dbx 快照，仅依赖宿主自动下发，观察是否回落参数弹窗。
  await page.goto(`${base}${args.path}`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForSelector('#dbx-ide-frame', { state: 'attached', timeout: 30000 });
  await page.waitForSelector('[data-variable-panel]', { state: 'attached', timeout: 20000 });
  result.steps.cleanStateMessages = await page.evaluate(() => globalThis.__DBX_MSG_LOG__ ?? []);
  result.steps.sqlProbeCleanState = await probeSql(page, '03-dbx-editor-clean-state');

  result.finishedAt = new Date().toISOString();
  await browser.close();
  console.log(JSON.stringify(result, null, 2));
}

main().catch(async (err) => {
  result.fatal = String(err && err.stack ? err.stack : err).slice(0, 1200);
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = 1;
});

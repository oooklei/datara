/**
 * SSH 共享入口 + DAG 资源下拉 UI 验证（Playwright，1.9 E2E）。
 *
 * 验收点（2026-11-01 用户三项裁定的 E2E 部分）：
 *   A) /dep/ssh：每行有「共享」按钮 → 弹窗用户下拉有真实用户 → 提交成功出现「已共享」提示
 *      （隐患2：SSH 节点共享无前端入口 — UI 验收）
 *   B) /p/{pid}/dag：工作流列表 → 海豚画布 iframe → 打开 SQL 节点「当前节点设置」
 *      → 「资源」下拉出现 datara-p33-* 文件（任务3：脚本同步海豚资源中心 — UI 验收）
 *
 * 用法（token 只经环境变量注入，绝不落盘/入库/入 URL）：
 *   $env:DATARA_TEST_TOKEN = <短时 token>
 *   node deploy/ssh-share-dag-ui-verify.mjs --base http://192.168.1.9:8090 --pid 33 --out .evidence/ssh-dag-e2e
 *
 * 产出：JSON 结果（stdout）+ 分步截图。
 */
import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

function parseArgs(argv) {
  const args = { base: 'http://192.168.1.9:8090', out: '.evidence/ssh-dag-e2e', pid: '33' };
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
  badResponses: [],
  screenshots: [],
};

async function shot(page, name) {
  const file = path.join(outDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  result.screenshots.push(path.relative(process.cwd(), file));
}

const vis = () => {
  const r = el.getBoundingClientRect();
  return r.width > 3 && r.height > 3;
};

async function main() {
  await fs.mkdir(outDir, { recursive: true });
  if (!token) throw new Error('DATARA_TEST_TOKEN 未设置（token 只经环境变量注入）');

  // 本机系统代理不可用，直连 192.168.1.9 必须绕过代理（同 dbx-ide-ui-verify）。
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-proxy-server', '--proxy-bypass-list=*'],
  });
  const context = await browser.newContext({ viewport: { width: 1728, height: 1000 } });
  await context.addInitScript((value) => {
    globalThis.__DATARA_TEST_TOKEN__ = value;
  }, token);
  const page = await context.newPage();

  page.on('console', (msg) => {
    if (msg.type() === 'error') result.consoleErrors.push(msg.text().slice(0, 300));
  });
  page.on('pageerror', (err) => result.pageErrors.push(String(err).slice(0, 300)));
  page.on('response', (res) => {
    if (res.status() >= 400) result.badResponses.push({ status: res.status(), url: res.url().replace(base, '') });
  });

  /* ================= Part A：/dep/ssh 共享入口 ================= */

  const respA = await page.goto(`${base}/dep/ssh`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  result.steps.sshGoto = { status: respA?.status() ?? 0, finalPath: new URL(page.url()).pathname };
  await page.waitForSelector('[data-node-list]', { state: 'attached', timeout: 30000 });
  await page.waitForFunction(() => document.querySelectorAll('[data-node-id]').length > 0, { timeout: 30000 });
  result.steps.sshRows = await page.evaluate(() =>
    [...document.querySelectorAll('[data-node-id]')].map((r) => ({
      id: r.getAttribute('data-node-id'),
      text: (r.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 120),
      hasShare: !!r.querySelector('[data-share]'),
      hasEdit: !!r.querySelector('[data-edit]'),
    })),
  );
  await shot(page, '01-ssh-list');

  // 打开第一行的共享弹窗
  await page.locator('[data-node-id]').first().locator('[data-share]').click();
  const dialog = page.locator('form[aria-label="共享 SSH 节点"]');
  await dialog.waitFor({ state: 'visible', timeout: 10000 });
  result.steps.shareDialogOpened = true;
  // 等用户下拉加载（enabled 用户 → option value 非空）
  await page
    .waitForFunction(
      () => {
        const sel = document.querySelector('[data-share-user]');
        return !!sel && [...sel.options].some((o) => !o.disabled && o.value !== '');
      },
      { timeout: 15000 },
    )
    .catch(() => {});
  result.steps.shareUserOptions = await page.evaluate(() =>
    [...(document.querySelector('[data-share-user]')?.options ?? [])].map((o) => ({
      value: o.value,
      text: o.text,
      disabled: o.disabled,
    })),
  );
  await shot(page, '02-ssh-share-dialog');

  const admin = result.steps.shareUserOptions.find((o) => o.text.startsWith('admin'));
  const target = admin ?? result.steps.shareUserOptions.find((o) => !o.disabled && o.value !== '');
  if (target) {
    await page.locator('[data-share-user]').selectOption(target.value);
    const shareRespPromise = page
      .waitForResponse((r) => /\/ssh-nodes\/\d+\/share/.test(r.url()) && r.request().method() === 'POST', { timeout: 15000 })
      .catch(() => null);
    await page.locator('[data-share-confirm]').click();
    const shareResp = await shareRespPromise;
    result.steps.shareSubmit = {
      targetUser: target.text,
      response: shareResp ? { status: shareResp.status(), body: await shareResp.json().catch(() => null) } : null,
    };
    // 等弹窗关闭 + 成功提示
    await page.waitForFunction(() => !document.querySelector('[data-share-user]'), { timeout: 10000 }).catch(() => {});
    const bodyText = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
    result.steps.sharedMessageVisible = bodyText.includes('已共享');
    result.steps.bodyAfterShare = bodyText.slice(0, 500);
  } else {
    result.steps.shareSubmit = { skipped: '无可选用户', error: await dialog.locator('[data-share-error]').textContent().catch(() => null) };
  }
  await shot(page, '03-ssh-after-share');

  /* ================= Part B：/p/{pid}/dag 资源下拉 ================= */

  const pid = args.pid;
  const respB = await page.goto(`${base}/p/${pid}/dag`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  result.steps.dagGoto = { status: respB?.status() ?? 0, finalPath: new URL(page.url()).pathname };
  await page.waitForSelector('[data-tc-wf-list]', { state: 'attached', timeout: 30000 });
  await page
    .waitForFunction(
      () => !!document.querySelector('[data-wf-table]') || !!document.querySelector('[data-wf-empty],[data-wf-error],[data-wf-loading]'),
      { timeout: 30000 },
    )
    .catch(() => {});
  result.steps.wfList = await page.evaluate(() => ({
    rows: [...document.querySelectorAll('[data-wf-row]')].map((r) => ({
      code: r.getAttribute('data-wf-row'),
      name: r.querySelector('[data-wf-open]')?.textContent?.trim() ?? '',
    })),
    hint: document.querySelector('[data-tc-wf-empty],[data-wf-empty],[data-wf-error],[data-wf-loading]')?.textContent?.trim() ?? '',
  }));
  await shot(page, '04-dag-wf-list');

  if (result.steps.wfList.rows.length > 0) {
    await page.locator('[data-wf-open]').first().click();
    await page.locator('[data-tc-ds-frame]').waitFor({ state: 'attached', timeout: 30000 });

    // 等海豚帧出现并 boot
    let dsFrame = null;
    for (let i = 0; i < 90; i += 1) {
      dsFrame = page.frames().find((f) => /\/dolphinscheduler\/ui\/projects\//.test(f.url()));
      if (dsFrame) break;
      await page.waitForTimeout(500);
    }
    result.steps.dsFrameUrl = dsFrame ? dsFrame.url() : null;
    if (dsFrame) {
      // 等画布节点出现（x6 节点或含 task/node 类名的元素）
      let canvasDump = null;
      for (let i = 0; i < 60; i += 1) {
        canvasDump = await dsFrame.evaluate(() => {
          const x6 = [...document.querySelectorAll('.x6-node')].map((el) => ({
            cls: String(el.getAttribute('class') ?? '').slice(0, 120),
            text: (el.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 80),
          }));
          return { x6Count: x6.length, x6 };
        });
        if (canvasDump.x6Count > 0) break;
        await page.waitForTimeout(1000);
      }
      result.steps.canvas = canvasDump;
      await shot(page, '05-ds-canvas');

      // 选 SQL 节点（匹配文本，兜底第一个），先单击后双击兼容两种交互
      const sqlNode = dsFrame.locator('.x6-node', { hasText: /sql/i }).first();
      const anyNode = dsFrame.locator('.x6-node').first();
      const nodeLoc = (await sqlNode.count()) > 0 ? sqlNode : anyNode;

      const dumpPanels = () =>
        dsFrame.evaluate(() => {
          const v = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 3 && r.height > 3;
          };
          const grab = (sel) =>
            [...document.querySelectorAll(sel)].filter(v).map((el) => ({
              cls: String(el.getAttribute('class') ?? '').slice(0, 100),
              text: (el.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 200),
            }));
          return {
            drawers: grab('.n-drawer, [class*="drawer"]'),
            modals: grab('[role="dialog"], .n-modal, [class*="modal"]'),
          };
        });

      await nodeLoc.click({ timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(1500);
      result.steps.panelAfterClick = await dumpPanels();
      const opened =
        (result.steps.panelAfterClick.drawers.length + result.steps.panelAfterClick.modals.length) > 0;
      if (!opened) {
        await nodeLoc.dblclick({ timeout: 10000 }).catch(() => {});
        await page.waitForTimeout(2000);
        result.steps.panelAfterDblclick = await dumpPanels();
      }
      await shot(page, '06-node-settings');

      // 在设置面板中定位「资源」字段并点开下拉，读选项
      const resource = await dsFrame.evaluate(() => {
        const v = (el) => {
          const r = el.getBoundingClientRect();
          return r.width > 3 && r.height > 3;
        };
        const items = [...document.querySelectorAll('.n-form-item, [class*="form-item"]')].filter(v);
        const hit = items.find((el) => /资源/.test(el.textContent ?? ''));
        if (!hit) {
          return {
            found: false,
            labels: items.map((el) => (el.querySelector('.n-form-item-label, label')?.textContent ?? '').trim()).filter(Boolean).slice(0, 30),
          };
        }
        const selection = hit.querySelector('.n-tree-select .n-base-selection, .n-select .n-base-selection, .n-base-selection');
        const label = (hit.querySelector('.n-form-item-label, label')?.textContent ?? '').trim();
        return { found: true, label, hasSelection: !!selection };
      });
      result.steps.resourceField = resource;

      if (resource.found && resource.hasSelection) {
        const selLoc = dsFrame.locator(
          '.n-form-item:has-text("资源") .n-tree-select .n-base-selection, .n-form-item:has-text("资源") .n-select .n-base-selection',
        ).first();
        await selLoc.click({ timeout: 10000 });
        // 资源下拉为本 fork 自定义选项列表（非 naive-ui menu）：按可见文本匹配文件名，轮询直至出现。
        let options = [];
        for (let i = 0; i < 15; i += 1) {
          options = await dsFrame.evaluate(() => {
            const v = (el) => {
              const r = el.getBoundingClientRect();
              return r.width > 3 && r.height > 3;
            };
            const names = new Set();
            for (const el of document.querySelectorAll('div, li, span, label, p')) {
              if (!v(el)) continue;
              const own = [...el.childNodes]
                .filter((n) => n.nodeType === Node.TEXT_NODE)
                .map((n) => n.textContent?.trim() ?? '')
                .join('');
              if (/^datara-[A-Za-z0-9._-]+$/.test(own)) names.add(own);
            }
            return [...names].sort();
          });
          if (options.length > 0) break;
          await page.waitForTimeout(500);
        }
        result.steps.resourceOptions = { count: options.length, options: options.slice(0, 50) };
        result.steps.resourceHasDataraFiles = options.some((t) => t.startsWith('datara-p33-'));
      } else {
        result.steps.resourceOptions = { skipped: '未找到资源下拉（见 resourceField 诊断）' };
      }
      await shot(page, '07-resource-options');
    } else {
      result.steps.dsFrameUrl = null;
      result.steps.canvasNote = '海豚 iframe 未出现（画布/会话未就绪）';
    }
  } else {
    result.steps.canvasNote = '无工作流定义可打开';
  }

  result.finishedAt = new Date().toISOString();
  await browser.close();
  console.log(JSON.stringify(result, null, 2));
}

main().catch(async (err) => {
  result.fatal = String(err && err.stack ? err.stack : err).slice(0, 1200);
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = 1;
});

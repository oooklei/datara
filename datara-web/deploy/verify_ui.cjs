/* 1.9 前端浏览器验证（端点合一重构）：
   登录 → palette 7 项 → 新建画布默认 8 节点链 + 拖入 3 编排组件展开 3 链/无执行组件
   → Inspector baseMode 三分拣切换 → wf_orch_tgt_base 探测候选联动（prefix 路径）
   → 三用例「校验」0 错误 0 警告 */
const { chromium } = require('C:/Users/Administrator/.trae-cn/skills/gstack/node_modules/playwright');

const BASE = 'http://192.168.1.9:8090'; // datara-web 前端（80 端口 nginx 302 → /ui/ 非本项目）
const SHOTS = __dirname + '/shots/';
const INSPECTOR_SEL = '.inspector, [class*="inspector"], [class*="detail-panel"], [class*="node-form"]';
const failures = [];
function check(name, ok, extra) {
  console.log(`[CHECK] ${ok ? 'PASS' : 'FAIL'} - ${name}${extra ? ' | ' + extra : ''}`);
  if (!ok) failures.push(name);
}

async function inspectorText(page) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    return el ? el.innerText : '';
  }, INSPECTOR_SEL);
}

/** Inspector 内全量可见叶子文本（跳过 display:none 折叠区与容器节点） */
async function visibleLeafs(page) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return [];
    const out = [];
    for (const e of el.querySelectorAll('*')) {
      if (e.children.length) continue;
      const t = (e.textContent || '').trim();
      if (!t || t.length > 50 || t === '*') continue;
      if (!e.offsetParent && e.getClientRects().length === 0) continue;
      out.push(t);
    }
    return Array.from(new Set(out));
  }, INSPECTOR_SEL);
}

/** 打开画布并 reload（保证画布/弹窗状态干净，localStorage token 保留） */
async function openCanvas(page, doc) {
  const url = BASE + '/#/dag?tab=edit&type=sync' + (doc ? '&doc=' + doc : '');
  await page.goto(url);
  await page.reload();
  await page.waitForSelector('.vue-flow', { timeout: 20000 });
  await page.waitForTimeout(1800);
}

async function canvasNodes(page) {
  return page.evaluate(() => {
    return Array.from(document.querySelectorAll('.vue-flow__node')).map((n) => ({
      id: n.getAttribute('data-id') || '',
      text: (n.innerText || '').split('\n')[0].trim(),
    }));
  });
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1680, height: 950 } });
  page.on('pageerror', (e) => console.log('[pageerror]', e.message));
  page.on('response', (r) => {
    if (r.url().includes('/api/') && !r.ok()) console.log('[net]', r.status(), r.url());
  });

  // 1. 登录
  await page.goto(BASE + '/login');
  await page.fill('input.lg-input', 'admin');
  await page.fill('input[placeholder="请输入密码"]', 'Admin@123');
  await page.click('button.lg-submit');
  let tok = '';
  for (let i = 0; i < 30 && !tok; i++) {
    await page.waitForTimeout(500);
    tok = await page.evaluate(() => localStorage.getItem('datara_token') || '');
  }
  if (!tok) throw new Error('登录失败：datara_token 为空');
  console.log('[1] login OK，token 长度', tok.length);

  // 2. palette 7 项断言（3 编排 + 4 细项；端点合一后无「源端选择/目标端选择」）
  await openCanvas(page, 'wf_orch_src_base');
  const palItems = await page.locator('.pal-item .p-name').allInnerTexts();
  console.log('[2] palette 组件项数:', palItems.length);
  const want = ['源表基准编排', '目标表基准编排', '文件同步编排',
    '端点选择', '字段映射-复制', '字段映射-联合', '条件设定'];
  const missing = want.filter((w) => !palItems.some((t) => t.includes(w)));
  check('palette 7 项在列', missing.length === 0, missing.length ? 'MISSING: ' + missing.join(' | ') : '7/7');
  const stale = ['源端选择', '目标端选择'].filter((w) => palItems.some((t) => t.includes(w)));
  check('palette 无旧版「源端选择/目标端选择」细项', stale.length === 0, stale.join(','));

  // 3. 新建画布（无 doc = 默认同步编排模板）：默认 8 节点链且无执行组件
  await openCanvas(page, '');
  const before = (await canvasNodes(page)).length;
  const beforeNodes = await canvasNodes(page);
  console.log('[3] 新建画布默认节点:', beforeNodes.map((n) => n.id).join(' , '));
  check('新建画布默认 8 节点链（start/sql/ep/map/cond/assert/notify/end）', before === 8, `实际 ${before}`);

  // 3b. 依次拖入 3 个编排组件（HTML5 drag），每链展开 8 节点
  const canvas = await page.locator('.vue-flow').first().boundingBox();
  const names = ['源表基准编排', '目标表基准编排', '文件同步编排'];
  let dropped = 0;
  for (let i = 0; i < names.length; i++) {
    const src = `.pal-item:has-text("${names[i]}")`;
    try {
      await page.dragAndDrop(src, '.vue-flow', {
        targetPosition: { x: canvas.width * 0.5 + (i % 2) * 240, y: 100 + Math.floor(i / 2) * 300 },
      });
      await page.waitForTimeout(1200);
      dropped++;
      const nodes = await canvasNodes(page);
      console.log(`[3] 拖入 ${names[i]} 后节点数=${nodes.length}`);
      if (dropped === 1) {
        check('拖入 1 编排组件展开为 8 节点链（start/sql/ep/map/cond/assert/notify/end）', nodes.length === before + 8, `期望 ${before + 8}，实际 ${nodes.length}`);
      }
    } catch (e) {
      console.log(`[3] 拖入失败: ${names[i]} (${String(e).slice(0, 80)})`);
    }
  }
  check('3 个编排组件均拖入成功', dropped === 3, `dropped=${dropped}`);
  const allNodes = await canvasNodes(page);
  check('拖入 3 组件后每链展开 8 节点（共 +24）', allNodes.length === before + 24, `期望 ${before + 24}，实际 ${allNodes.length}`);
  const execNodes = allNodes.filter((n) => /(^|[^a-z_])(sync|file_sync)([^a-z_]|$)/i.test(n.id) || /file_sync/.test(n.text));
  check('画布无 type=sync/file_sync 执行组件节点（设计态 runtimeOnly）', execNodes.length === 0, execNodes.map((n) => n.id).join(','));
  await page.screenshot({ path: SHOTS + 'ui2_chains.png' });

  // 4. Inspector：点新拖入的端点选择节点 → baseMode 三分拣切换
  const epNode = page.locator('.vue-flow__node', { hasText: '端点选择' }).last();
  if (await epNode.count()) {
    await epNode.click({ force: true });
    await page.waitForTimeout(900);
    const baseSel = page.locator(
      INSPECTOR_SEL.split(',').map((s) => s.trim() + ' select:has(option[value="src_base"])').join(', ')
    ).first();
    check('Inspector 存在基准类型（baseMode）下拉', (await baseSel.count()) === 1, `count=${await baseSel.count()}`);
    const modes = [
      ['src_base', (v) => v.some((t) => t.includes('目标表')) && !v.some((t) => t.includes('文件类型')) && !v.some((t) => t.includes('联动探测')), '源端选表 + 目标端表字段，无文件/探测字段'],
      ['tgt_base', (v) => v.some((t) => t.includes('联动探测匹配表')) && !v.some((t) => t.includes('文件类型')), '探测区块出现（联动探测匹配表）；probe 未开时子字段按 showIf 隐藏'],
      ['file_sync', (v) => (v.some((t) => t.includes('文件类型')) || v.some((t) => t.includes('文件路径'))) && !v.some((t) => t.includes('联动探测')) && !v.some((t) => t.includes('匹配规则')), '文件字段（路径/类型/分隔符/编码/表头行数）'],
    ];
    for (const [mode, pred, desc] of modes) {
      await baseSel.selectOption(mode);
      await page.waitForTimeout(800);
      const vis = await visibleLeafs(page);
      const ok = pred(vis);
      console.log(`[4] baseMode=${mode} 可见叶子: ${vis.filter((t) => t.length > 2).slice(0, 24).join(' | ')}`);
      check(`baseMode=${mode} 表单分拣正确（${desc}）`, ok);
      await page.screenshot({ path: SHOTS + `ui3_basemode_${mode}.png` });
    }
  } else {
    check('拖入链内找到端点选择节点', false, '未找到');
  }

  // 5. 探测候选联动：wf_orch_tgt_base（tgt_base seed）→ prefix 探测 → 候选含三 schema → 全选回写
  await openCanvas(page, 'wf_orch_tgt_base');
  const ep2 = page.locator('.vue-flow__node', { hasText: '端点选择' }).first();
  if (await ep2.count()) {
    await ep2.click({ force: true });
    await page.waitForTimeout(1200);
    const baseSel2 = page.locator(
      INSPECTOR_SEL.split(',').map((s) => s.trim() + ' select:has(option[value="src_base"])').join(', ')
    ).first();
    const mtSel = page.locator(
      INSPECTOR_SEL.split(',').map((s) => s.trim() + ' select:has(option[value="prefix"])').join(', ')
    ).first();
    await baseSel2.selectOption('tgt_base');
    await page.waitForTimeout(700);
    await mtSel.selectOption('prefix');
    await page.waitForTimeout(500);
    const mp = page.locator('input[placeholder="如 ods_order"]').first();
    await mp.fill('ods_order');
    // 点开目标表 picker 触发源端库表树拉取（树为按需加载，是探测候选的数据通道）
    const picker = page.locator('input[placeholder="选择库 / 表…"]').first();
    if (await picker.count()) {
      await picker.click();
      await page.waitForTimeout(3000);
      await page.keyboard.press('Escape');
      await page.waitForTimeout(800);
    } else {
      console.log('[5] 未找到目标表 picker 输入框');
    }
    // 轮询候选区
    let hits = [];
    for (let i = 0; i < 8; i++) {
      hits = await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (!el) return [];
        return Array.from(el.querySelectorAll('.probe-item')).map((l) => (l.innerText || '').trim());
      }, INSPECTOR_SEL);
      if (hits.length) break;
      await page.waitForTimeout(1500);
    }
    console.log('[5] 探测候选:', JSON.stringify(hits));
    const cands = ['ec_retail.ods_order', 'ec_retail_east.ods_order', 'ec_retail_south.ods_order'];
    const hitC = cands.filter((c) => hits.some((h) => h === c || h.includes(c)));
    check('探测候选出现 ec_retail/ec_retail_east/ec_retail_south 三 schema', hitC.length === 3, `命中 ${hitC.length}/3`);
    // 全选 → probeResult 文本回写（勾选 ↔ 文本双向同步）
    const selAll = page.locator('button:has-text("全选")').first();
    if ((await selAll.count()) && hits.length) {
      await selAll.click();
      await page.waitForTimeout(600);
      const prVal = await page.locator('input[placeholder^="如 ec_retail."]').first().inputValue().catch(() => '');
      console.log('[5] 全选后参与 schema/表 文本:', prVal.slice(0, 120));
      check('全选勾选回写 probeResult 文本（双向同步）', cands.every((c) => prVal.includes(c)), prVal.slice(0, 80));
      const checkedCnt = await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        return el ? el.querySelectorAll('.probe-item input:checked').length : -1;
      }, INSPECTOR_SEL);
      check('候选区勾选态生效', checkedCnt === hits.length, `checked=${checkedCnt}/${hits.length}`);
    }
    await page.screenshot({ path: SHOTS + 'ui4_probe.png' });
  } else {
    check('wf_orch_tgt_base 画布端点选择节点存在', false, '未找到');
  }

  // 6. 三用例「校验」0 错误 0 警告（各自 reload 后干净画布校验）
  for (const doc of ['wf_orch_src_base', 'wf_orch_tgt_base', 'wf_orch_file_sync']) {
    await openCanvas(page, doc);
    const btn = page.locator('button:has-text("校验")').first();
    if (!(await btn.count())) { check(`${doc} 校验按钮存在`, false); continue; }
    await btn.click();
    await page.waitForTimeout(2500);
    const res = await page.evaluate(() => {
      const win = document.querySelector('.float-win');
      return win ? win.innerText.replace(/\n+/g, ' | ').slice(0, 700) : '(未找到 .float-win)';
    });
    console.log(`[6] ${doc} 校验结果弹窗: ${res}`);
    // 0 错误 0 警告的两种渲染形态：成功文案「校验通过，未发现问题」或计数文案「共 0 错误 · 0 警告」
    check(`${doc} 校验 0 错误 0 警告`,
      /校验通过，未发现问题/.test(res) || (/共\s*0\s*个?\s*错误/.test(res) && /0\s*个?\s*警告/.test(res)), res);
    await page.screenshot({ path: SHOTS + `ui5_validate_${doc}.png` });
  }

  await browser.close();
  if (failures.length) {
    console.log(`VERIFY_FAILED (${failures.length}): ${failures.join(' | ')}`);
    process.exit(2);
  }
  console.log('VERIFY_ALL_PASS');
})().catch((e) => { console.error('FATAL', e); process.exit(1); });

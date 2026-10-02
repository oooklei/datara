/* 1.9 端点合一重构 UI 交互验收（verify_ui.cjs 的交互补充，不改产品代码）：
   C  UI 触发运行（试运行→运行对话框→提交）+ 轮询实例 + 运行实例页详情抽屉
      （断言 sys_exec_ 物化 sync 步骤 + read_rows/write_rows 输出 pill）
   B1 删边→引用消失（右键边→删除连线；字段映射 Inspector 输入引用清空）
   B2 拖线重建→引用恢复（mouse down/move/up 连 sourceRef 手柄→字段映射左口）
   纪律：预制用例画布只读（仅 C 打开 wf_orch_src_base 点试运行，不做任何编辑/保存）；
   B1/B2 在临时新建定义的画布上进行（脚本结束删除该临时定义，净写入为零）；
   全程不点「保存」。
   环境变量：REUSE_INSTANCE=<实例id> 跳过触发运行，直接对该实例做 C4/C5 详情断言
   （避免重复触发运行）；SCRATCH_PREFIX 清理名前缀默认 ui_verify_scratch_。 */
const { chromium } = require('C:/Users/Administrator/.trae-cn/skills/gstack/node_modules/playwright');

const BASE = 'http://192.168.1.9:8090'; // datara-web 前端（80 端口为另一项目，勿用）
const SHOTS = __dirname + '/shots/';
const WF = 'wf_orch_src_base'; // 预制用例（code 92）
const CODE = 92;
const PRESETS = ['wf_orch_src_base', 'wf_orch_tgt_base', 'wf_orch_file_sync'];
const SCRATCH_PREFIX = 'ui_verify_scratch_';
const REUSE_INSTANCE = process.env.REUSE_INSTANCE || '';

const failures = [];
function check(name, ok, extra) {
  console.log(`[CHECK] ${ok ? 'PASS' : 'FAIL'} - ${name}${extra ? ' | ' + extra : ''}`);
  if (!ok) failures.push(name);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 页面内 fetch（携带 datara_token，Envelope {code,msg,data}） */
async function api(page, method, path, body) {
  return page.evaluate(async ({ m, p, b }) => {
    const token = localStorage.getItem('datara_token') || '';
    const res = await fetch('/api/v1' + p, {
      method: m,
      headers: { token, ...(b ? { 'Content-Type': 'application/json' } : {}) },
      body: b ? JSON.stringify(b) : undefined,
    });
    return res.json().catch(() => null);
  }, { m: method, p: path, b: body ?? null });
}

/** 打开画布并 reload（保证画布/弹窗状态干净，localStorage token 保留；同 verify_ui.cjs） */
async function openCanvas(page, doc) {
  const url = BASE + '/#/dag?tab=edit&type=sync' + (doc ? '&doc=' + doc : '');
  await page.goto(url);
  await page.reload();
  await page.waitForSelector('.vue-flow', { timeout: 20000 });
  await page.waitForTimeout(2000);
}

/** 画布节点：data-id + 全量 innerText（首行是图标字符，节点名在后续行，勿只取首行） */
async function canvasNodes(page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('.vue-flow__node')).map((n) => ({
      id: n.getAttribute('data-id') || '',
      text: (n.innerText || '').replace(/\s+/g, ' ').trim(),
    })));
}

/** 找 ep→map 之间的边：优先语义 data-id（e_{source}_{target}），退化几何匹配（横跨两节点间隙） */
async function findEdgeBetweenGeo(page, epId, mapId) {
  if (!epId || !mapId) return null;
  const direct = page.locator(`.vue-flow__edge[data-id="e_${epId}_${mapId}"]`);
  if (await direct.count()) return `e_${epId}_${mapId}`;
  return page.evaluate(({ s, t }) => {
    const a = document.querySelector(`.vue-flow__node[data-id="${s}"]`);
    const b = document.querySelector(`.vue-flow__node[data-id="${t}"]`);
    if (!a || !b) return null;
    const ra = a.getBoundingClientRect(); const rb = b.getBoundingClientRect();
    const lo = Math.min(ra.right, rb.right) - 10;
    const hi = Math.max(ra.left, rb.left) + 10;
    const yLo = Math.min(ra.y, rb.y) - 6; const yHi = Math.max(ra.bottom, rb.bottom) + 6;
    for (const e of document.querySelectorAll('.vue-flow__edge')) {
      const r = e.getBoundingClientRect();
      if (r.width < 1 && r.height < 1) continue;
      if (r.x >= lo && r.right <= hi && r.y >= yLo && r.bottom <= yHi) return e.getAttribute('data-id');
    }
    return null;
  }, { s: epId, t: mapId });
}

/** Inspector 全部 upstream-refs 表格：[0] = 「输入（上游节点输出…）」字段（form 首个 upstream-refs） */
async function readUrTables(page) {
  return page.evaluate(() => {
    const tables = Array.from(document.querySelectorAll('.ur-table'));
    return tables.map((tb) => ({
      rows: Array.from(tb.querySelectorAll('.ur-row select')).map((sel) => {
        const opt = sel.selectedOptions[0];
        return { value: sel.value, label: opt ? opt.textContent.trim() : '' };
      }),
      empty: (tb.querySelector('.ur-empty')?.textContent || '').trim(),
    }));
  });
}

/** 打开指定实例的详情抽屉并做 C4/C5 断言（不触发运行） */
async function verifyInstanceDetail(page, inst) {
  await page.evaluate(() => { location.hash = '#/dag/instances'; });
  await page.waitForSelector('.tbl', { timeout: 15000 });
  await page.waitForTimeout(1200);
  const id18 = inst.instanceId.slice(0, 18);
  const row = page.locator('.tbl tbody tr', { hasText: id18 }).first();
  check('C4 运行实例列表页可见本次实例行', (await row.count()) > 0, `匹配前缀 ${id18}`);
  await row.locator('button:has-text("详情")').first().click();
  const drawer = page.locator('.el-drawer', { hasText: '实例详情' }).first();
  await drawer.waitFor({ state: 'visible', timeout: 8000 });
  await page.waitForTimeout(2500); // 任务表 + 3s 轮询首帧
  const drawerText = await drawer.innerText();
  check('C4 详情抽屉标题含本次实例 id', drawerText.includes(inst.instanceId), inst.instanceId);

  // API 交叉验证：taskInstances 有 sys_exec_ 前缀物化 sync 步骤
  const detail = await api(page, 'GET', `/instances/${encodeURIComponent(inst.instanceId)}`);
  const tasks = detail?.data?.taskInstances ?? [];
  const sysExec = tasks.filter((t) => String(t.nodeId).startsWith('sys_exec_'));
  const syncStep = sysExec.find((t) => t.nodeType === 'sync') ?? null;
  check('C5 实例详情含 sys_exec_ 前缀步骤且 type=sync（API 交叉）',
    sysExec.length > 0 && !!syncStep,
    `taskInstances=${tasks.length} sys_exec_=${sysExec.length} ` +
    (sysExec.length ? `nodeIds=${sysExec.map((t) => t.nodeId).join(',')} types=${sysExec.map((t) => t.nodeType).join(',')}` : ''));
  const outs = syncStep?.outputs ?? {};
  console.log('[C] sync 步骤 outputs:', JSON.stringify(outs).slice(0, 240));

  // DOM 断言：详情面板展示 sync 类型任务行 + 读写行数输出 pill（实际键名 read_rows/write_rows）
  check('C5 详情面板展示 type=sync 任务行（nodeType 列可见）', /(^|\W)sync(\W|$)/.test(drawerText), '');
  for (const [k, alt] of [['read_rows', 'rows_read'], ['write_rows', 'rows_written']]) {
    const v = outs[k] ?? outs[alt];
    if (v === undefined) { console.log(`[C] outputs 无 ${k}（如实记录）`); continue; }
    check(`C5 详情面板含 ${k} 输出 pill（值一致）`, drawerText.includes(`${k}=${v}`),
      `${k}=${v}；面板片段=${(drawerText.match(new RegExp(`${k}=[^\\s]*`)) || ['(未渲染)'])[0]}`);
  }
  await page.screenshot({ path: SHOTS + 'c3_instance_detail.png' });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(800);
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1680, height: 950 } });
  const consoleErrors = [];
  page.on('pageerror', (e) => { consoleErrors.push('pageerror: ' + e.message); console.log('[pageerror]', e.message); });
  page.on('console', (m) => { if (m.type() === 'error') { consoleErrors.push('console: ' + m.text()); console.log('[console.error]', m.text().slice(0, 200)); } });
  page.on('response', (r) => {
    if (r.url().includes('/api/') && !r.ok()) console.log('[net]', r.status(), r.url());
  });

  // ============ 登录 ============
  await page.goto(BASE + '/login');
  await page.fill('input.lg-input', 'admin');
  await page.fill('input[placeholder="请输入密码"]', 'Admin@123');
  await page.click('button.lg-submit');
  let tok = '';
  for (let i = 0; i < 30 && !tok; i++) {
    await sleep(500);
    tok = await page.evaluate(() => localStorage.getItem('datara_token') || '');
  }
  if (!tok) throw new Error('登录失败：datara_token 为空');
  console.log('[0] login OK，token 长度', tok.length);

  // 防御清理：上次异常退出可能遗留的临时定义（按名称前缀识别，只删本脚本产物）
  const defs0 = await api(page, 'GET', '/workflow-definitions?page_no=1&page_size=200');
  const stale = (defs0?.data?.list ?? []).filter((d) => String(d.name || '').startsWith(SCRATCH_PREFIX));
  for (const s of stale) {
    const r = await api(page, 'DELETE', `/workflow-definitions/${encodeURIComponent(s.id)}`);
    console.log(`[0] 清理遗留临时定义 ${s.id}: code=${r?.code}`);
  }

  // 安全基线：三个预制用例定义当前版本（验收结束复核未被写）
  const ver0 = {};
  for (const d of (defs0?.data?.list ?? [])) if (PRESETS.includes(d.id)) ver0[d.id] = d.version;
  console.log('[0] 预制用例版本基线:', JSON.stringify(ver0));

  // ============ C. UI 触发运行 + 运行详情 ============
  let inst = null;
  if (REUSE_INSTANCE) {
    console.log(`[C] REUSE_INSTANCE=${REUSE_INSTANCE}：跳过触发，直接复做详情断言（不重复触发运行）`);
    const d = await api(page, 'GET', `/instances/${encodeURIComponent(REUSE_INSTANCE)}`);
    inst = d?.data ?? null;
    check('C3 复用实例可查询', !!inst && inst.state === 'success', inst ? `state=${inst.state}` : '未查到');
  } else {
    await openCanvas(page, WF);
    const runBtn = page.locator('button.tb-btn.run');
    const runBtnText = (await runBtn.count()) ? (await runBtn.innerText()).trim() : '';
    check('C1 编辑页顶部工具栏存在运行入口（试运行按钮）', (await runBtn.count()) === 1 && /试运行|运行|执行|启动/.test(runBtnText), `text=${runBtnText}`);

    // 触发前实例快照（识别本次新实例）
    const before = await api(page, 'GET', `/instances?wf_code=${CODE}&page_no=1&page_size=50`);
    const beforeIds = new Set((before?.data?.list ?? []).map((r) => r.instanceId));
    console.log(`[C] 触发前 wf_code=${CODE} 实例数=${beforeIds.size}`);

    await runBtn.click();
    const dlg = page.locator('.el-dialog', { hasText: '运行工作流' }).last();
    await dlg.waitFor({ state: 'visible', timeout: 8000 });
    check('C1 点击试运行弹出运行对话框（手工运行页签）', (await dlg.count()) > 0 && /手工运行/.test(await dlg.innerText()), (await dlg.innerText()).split('\n')[0]);
    await page.screenshot({ path: SHOTS + 'c1_run_dialog.png' });

    await dlg.locator('button:has-text("提交运行")').click();
    let cmdMsg = '';
    try {
      const msg = page.locator('.el-message', { hasText: '运行命令已提交' }).first();
      await msg.waitFor({ state: 'visible', timeout: 10000 });
      cmdMsg = await msg.innerText();
    } catch { /* 轮询兜底 */ }
    console.log('[C] 提交回执:', cmdMsg || '(ElMessage 未捕获，改由实例轮询确认)');
    check('C2 运行命令提交成功（ElMessage：运行命令已提交 commandId）', /运行命令已提交/.test(cmdMsg), cmdMsg.slice(0, 60));
    await page.screenshot({ path: SHOTS + 'c2_run_submitted.png' });

    // 轮询实例（master 2s 内建实例；同步 8 万行约 1-3 分钟）
    for (let i = 0; i < 150; i++) {
      const list = await api(page, 'GET', `/instances?wf_code=${CODE}&page_no=1&page_size=50`);
      const rows = list?.data?.list ?? [];
      const mine = rows.find((r) => !beforeIds.has(r.instanceId));
      if (mine) {
        inst = mine;
        if (['success', 'failure', 'kill'].includes(mine.state)) break;
        if (i % 5 === 0) console.log(`[C] 实例 ${mine.instanceId} 状态=${mine.state}（${i * 4}s）`);
      }
      await sleep(4000);
    }
    check('C3 UI 触发产生新实例并达到终态 success', !!inst && inst.state === 'success',
      inst ? `id=${inst.instanceId} state=${inst.state} start=${inst.startTime} end=${inst.endTime}` : '超时未产生新实例（10min）');
  }
  if (inst) {
    try { await verifyInstanceDetail(page, inst); } catch (e) { check('C4/C5 详情断言执行', false, String(e).slice(0, 120)); }
  }

  // ============ B1/B2. 临时画布：删边→引用消失 / 拖线重建→引用恢复 ============
  // 说明：无 doc 的 URL 为空态（实测），UI 无「新建工作流」入口（DagListView 已不可达）；
  // 为满足「不在预制用例画布上改」，用后端同款接口创建一次性临时定义承载画布，验收后删除（净写入为零，且全程不点保存）。
  const created = await api(page, 'POST', '/workflow-definitions', { name: SCRATCH_PREFIX + Date.now().toString(36) });
  const scratchId = created?.data?.id ?? '';
  check('B0 临时画布定义已创建（验收后删除）', !!scratchId, `id=${scratchId}`);
  if (!scratchId) throw new Error('临时定义创建失败，B1/B2 无法进行');

  try {
    await openCanvas(page, scratchId);
    let nodes = await canvasNodes(page);
    console.log('[B] 临时画布初始节点数:', nodes.length);
    if (nodes.length === 0) {
      // 空定义 → 从 palette 拖入「源表基准编排」模板组件展开 8 节点链（HTML5 drag，verify_ui 已验证通路）
      let palItem = page.locator('.pal-item', { hasText: '源表基准编排' }).first();
      if (!(await palItem.isVisible().catch(() => false))) {
        const cat = page.locator('.pal-cat-head', { hasText: '同步' }).first();
        if (await cat.count()) { await cat.click(); await page.waitForTimeout(400); }
      }
      await page.dragAndDrop('.pal-item:has-text("源表基准编排")', '.vue-flow', {
        targetPosition: { x: 420, y: 140 },
      });
      await page.waitForTimeout(1800);
      nodes = await canvasNodes(page);
    }
    console.log('[B] 展开后节点:', nodes.map((n) => `${n.id}(${n.text})`).join(' , '));
    check('B0 临时画布展开 8 节点链（含 端点选择/字段映射-复制）',
      nodes.length === 8 && nodes.some((n) => n.text.includes('端点选择')) && nodes.some((n) => n.text.includes('字段映射-复制')),
      `实际 ${nodes.length}`);
    const epId = nodes.find((n) => n.text.includes('端点选择'))?.id ?? '';
    const mapId = nodes.find((n) => n.text.includes('字段映射-复制'))?.id ?? '';
    const mapNode = page.locator('.vue-flow__node', { hasText: '字段映射-复制' }).first();
    if (!epId || !mapId) throw new Error(`节点定位失败 epId=${epId} mapId=${mapId}`);

    // ---- B1 步骤1：点字段映射 → 引用含 端点选择/源端表 ----
    await mapNode.click({ force: true });
    await page.waitForTimeout(1000);
    let urTables = await readUrTables(page);
    const inputs0 = urTables[0] ?? { rows: [], empty: '(无输入引用表格)' };
    console.log('[B1] 引用(before):', JSON.stringify(inputs0));
    const refLabel0 = inputs0.rows.map((r) => r.label).join(' / ');
    check('B1-a 字段映射 Inspector 输入引用预置「端点选择·源端表」',
      inputs0.rows.some((r) => r.label.includes('端点选择') && r.label.includes('源端表')),
      `label="${refLabel0}" value="${inputs0.rows.map((r) => r.value).join(',')}"`);
    await page.screenshot({ path: SHOTS + 'b1_ref_before.png' });

    // ---- B1 步骤2：删除 端点选择→字段映射 的边（右键→删除连线；兜底 点选+Delete） ----
    const edgeId = await findEdgeBetweenGeo(page, epId, mapId);
    console.log('[B1] 目标边 data-id =', edgeId);
    if (!edgeId) {
      check('B1-b 找到 端点选择→字段映射 的边', false, '几何与语义均未匹配到边');
    } else {
      const edgeLoc = page.locator(`.vue-flow__edge[data-id="${edgeId}"]`).first();
      await edgeLoc.click({ button: 'right', force: true });
      await page.waitForTimeout(500);
      const ctxItem = page.locator('.ctx-item', { hasText: '删除连线' }).first();
      if (await ctxItem.isVisible().catch(() => false)) {
        await ctxItem.click();
        console.log('[B1] 经右键菜单「删除连线」删除边');
      } else {
        // 兜底：点选边 + Delete（GraphWorkbench onKeydown 批删选中边）
        await edgeLoc.click({ force: true });
        await page.waitForTimeout(300);
        await page.keyboard.press('Delete');
        console.log('[B1] 右键菜单未出现，走兜底：点选边 + Delete 键');
      }
      await page.waitForTimeout(900);
      const edgeGone = (await findEdgeBetweenGeo(page, epId, mapId)) === null;
      check('B1-b 端点选择→字段映射 的边已删除', edgeGone, `原边 ${edgeId}`);
      await page.screenshot({ path: SHOTS + 'b1_edge_deleted.png' });

      // ---- B1 步骤3：再点字段映射 → 引用清空（绝不保存） ----
      await mapNode.click({ force: true });
      await page.waitForTimeout(1000);
      urTables = await readUrTables(page);
      const inputs1 = urTables[0] ?? { rows: [], empty: '(无输入引用表格)' };
      console.log('[B1] 引用(after):', JSON.stringify(inputs1));
      const cleared = inputs1.rows.every((r) => !r.value) && inputs1.rows.every((r) => !r.label || r.label.includes('请选择'));
      check('B1-c 删边后字段映射输入引用为空/消失',
        inputs1.rows.length === 0 ? inputs1.empty.includes('未选择') : cleared,
        `rows=${inputs1.rows.length} labels="${inputs1.rows.map((r) => r.label).join(',')}" empty="${inputs1.empty}"`);
      await page.screenshot({ path: SHOTS + 'b1_ref_after.png' });
    }

    // ---- B2：mouse 拖线重建 sourceRef→字段映射（Vue Flow 手柄为 mouse 事件，HTML5 dragAndDrop 无效） ----
    const srcH = page.locator(`.vue-flow__handle[data-nodeid="${epId}"][data-handleid="sourceRef"]`).first();
    const tgtH = page.locator(`.vue-flow__node[data-id="${mapId}"] .vue-flow__handle[data-handlepos="left"]`).first();
    const sb = await srcH.boundingBox();
    const tb = await tgtH.boundingBox();
    check('B2-a 取到 sourceRef 源口与字段映射左口手柄', !!sb && !!tb,
      `src=${JSON.stringify(sb)} tgt=${JSON.stringify(tb)}`);
    let b2ok = false;
    if (sb && tb) {
      // 拖线前边集合快照：onConnect 重建的边 kind=branch 带 label「源端表」，label 元素撑大 bbox
      // 导致几何容差匹配失效 → 主判据用拖线前后 data-id 差集，几何匹配仅作兜底
      const edgesBefore = new Set(await page.evaluate(() =>
        Array.from(document.querySelectorAll('.vue-flow__edge')).map((e) => e.getAttribute('data-id') || '')));
      await page.mouse.move(sb.x + sb.width / 2, sb.y + sb.height / 2);
      await page.mouse.down();
      await page.mouse.move(tb.x + tb.width / 2, tb.y + tb.height / 2, { steps: 20 });
      await page.mouse.up();
      await page.waitForTimeout(1500);
      const edgesAfter = await page.evaluate(() =>
        Array.from(document.querySelectorAll('.vue-flow__edge')).map((e) => e.getAttribute('data-id') || ''));
      let edgeBack = edgesAfter.find((id) => !edgesBefore.has(id)) ?? null;
      if (!edgeBack) edgeBack = await findEdgeBetweenGeo(page, epId, mapId);
      console.log('[B2] 重建边 data-id =', edgeBack, `（差集法：before=${edgesBefore.size} after=${edgesAfter.length}）`);
      check('B2-b 拖线重建 端点选择(sourceRef)→字段映射 边', !!edgeBack, edgeBack ?? '未生成新边');
      await page.screenshot({ path: SHOTS + 'b2_edge_rebuilt.png' });

      await mapNode.click({ force: true });
      await page.waitForTimeout(1000);
      urTables = await readUrTables(page);
      const inputs2 = urTables[0] ?? { rows: [], empty: '(无输入引用表格)' };
      console.log('[B2] 引用(restored):', JSON.stringify(inputs2));
      b2ok = inputs2.rows.some((r) => r.label.includes('端点选择') && r.label.includes('源端表'));
      check('B2-c 引用恢复（输入引用再次为「端点选择·源端表」）', b2ok,
        `labels="${inputs2.rows.map((r) => r.label).join(',')}" values="${inputs2.rows.map((r) => r.value).join(',')}"`);
      await page.screenshot({ path: SHOTS + 'b2_ref_restored.png' });
    }
    if (!b2ok) console.log('[B2] FAIL 现场：截图 b2_edge_rebuilt/b2_ref_restored.png + console 错误已收集，不硬凑');
  } catch (e) {
    console.log('[B] 画布段异常（继续清理）:', String(e).slice(0, 200));
    failures.push('B-section-exception');
    try { await page.screenshot({ path: SHOTS + 'b_error_scene.png' }); } catch { /* 忽略 */ }
  } finally {
    // ============ 清理与安全复核（无保存写操作） ============
    if (scratchId) {
      const del = await api(page, 'DELETE', `/workflow-definitions/${encodeURIComponent(scratchId)}`);
      check('B0 临时画布定义已删除（净写入为零）', del?.code === 0, `code=${del?.code} msg=${del?.msg ?? ''}`);
    }
    const defs1 = await api(page, 'GET', '/workflow-definitions?page_no=1&page_size=200');
    const ver1 = {};
    for (const d of (defs1?.data?.list ?? [])) if (PRESETS.includes(d.id)) ver1[d.id] = d.version;
    check('安全复核：预制用例定义版本未变化（未发生任何保存）',
      PRESETS.every((k) => ver1[k] === ver0[k]), `before=${JSON.stringify(ver0)} after=${JSON.stringify(ver1)}`);
  }

  await browser.close();
  if (consoleErrors.length) console.log(`[console-errors] 共 ${consoleErrors.length} 条（见上方日志）`);
  if (failures.length) {
    console.log(`VERIFY_FAILED (${failures.length}): ${failures.join(' | ')}`);
    process.exit(2);
  }
  console.log('VERIFY_ALL_PASS');
})().catch((e) => { console.error('FATAL', e); process.exit(1); });

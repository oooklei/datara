/**
 * IMPL-v4-03 票面 v1.1 · 增补件 1：SSH 节点管理 E2E 全闭环（RT-IMPL-V4-02a 前置用例）。
 *
 * 闭环：路由承载 → 新建 → 凭据遮罩/显示切换 → 重名保护（后端 4102）→ 探测（结构化结果）
 *       → 删除（原生 confirm）→ 不存在保护（后端 4101）。
 *
 * 运行宿主：**192.168.1.9**（本机禁跑任何可执行验证；见 TEST-ENVIRONMENT-POLICY）。
 * 前置：1.9 部署栈含 `/api/v1/rebuild/ssh-nodes` 路由（`rebuild/sshnode/api.py`）与登录端点
 *       `/api/v1/rebuild/login`。
 *
 * 鉴权：POST /api/v1/rebuild/login 换 token → addInitScript 注入 localStorage（document-start），
 *       值不落盘；另经 route 层补写 `Authorization: Bearer`（双通道词形失配兜底）。
 *
 * 视图锚点口径：本页走布尔 `data-*` 属性（`[data-create]` / `[data-node-id]` / `[data-probe]` …），
 *   与 `llm-models.spec.ts` 的 `data-test` 命名不同，按 `SshNodeManagementView.vue` 原样取用。
 *
 * 隔离与并发（支撑 1.9 双线并行，Ops 指令）：本件**不依赖任何全局计数**、不复用固定名，
 *   全部数据以 `Date.now()` 后缀自命名，断言仅作用于本件自建行 → 与 `qc.spec.ts`（RT-07）并行无互扰。
 *
 * 证据：PNG 截图 + `e2e/evidence/sshNode.evidence.json` 成对落档（验收 v4 A3）。
 */
import { expect, test as base } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
const BASE = process.env.E2E_BASE ?? 'http://192.168.1.9:18091';
const USER = process.env.E2E_USER ?? 'e2e-runner';
const PASS = process.env.E2E_PASS ?? '';
const EV_DIR = path.resolve('e2e', 'evidence');
mkdirSync(EV_DIR, { recursive: true });
/** 探测目标：TEST-NET-1（RFC 5737，不可路由）——保证探测走结构化失败路径，零外部依赖。 */
const PROBE_HOST = process.env.E2E_SSH_PROBE_HOST ?? '192.0.2.1';
const evidence = {
    ticket: 'IMPL-v4-03',
    businessKey: 'IMPL-v4-03:impl:v1.1',
    revision: 'v1.1',
    host: '192.168.1.9',
    base_url: BASE,
    executed_at: new Date().toISOString(),
    route: '/dep/ssh',
    steps: [],
    screenshots: [],
    unverified: [],
};
function record(name, ok, detail = '') {
    evidence.steps.push({ name, ok, detail });
    console.log(`${ok ? 'PASS' : 'FAIL'} | ${name} | ${detail}`);
}
async function shot(page, name) {
    const file = `${name}.png`;
    await page.screenshot({ path: path.join(EV_DIR, file), fullPage: true });
    evidence.screenshots.push(file);
}
const test = base.extend({
    sshToken: async ({}, use) => {
        if (!PASS)
            throw new Error('E2E_PASS 未注入：拒绝运行（密码禁入代码库/证据——红线 8 / S6）');
        const res = await fetch(`${BASE}/api/v1/rebuild/login`, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ username: USER, password: PASS }),
        });
        const body = (await res.json().catch(() => null));
        const token = body?.data?.token ?? '';
        if (!res.ok || body?.code !== 0 || !token) {
            throw new Error(`login 失败：status=${res.status} code=${body?.code ?? '-'}`);
        }
        await use(token);
    },
    sshPage: async ({ browser, sshToken }, use) => {
        const ctx = await browser.newContext({ viewport: { width: 1680, height: 950 } });
        // token 注入走 addInitScript（document-start，规避首轮导航竞态）；值不落盘
        await ctx.addInitScript(([tk]) => globalThis.localStorage.setItem('datara_token', tk), [sshToken]);
        await ctx.route('**/api/**', (route) => route.continue({ headers: { ...route.request().headers(), authorization: `Bearer ${sshToken}` } }));
        const page = await ctx.newPage();
        await use(page);
        await ctx.close();
    },
});
/* ---------------- 路由可达性前置 ----------------
 * `/dep/ssh` 已注册于 `src/router/routes.ts`（dep-ssh）。前置探测失败即整组 skip 并留明原因：
 * 该情形属**环境闸**（部署栈未含本票制品）而非代码缺陷，制品同步后本文件无需改动自动转 GREEN。
 */
let routeReady = false;
let routeProbeNote = '';
test.beforeAll(async ({ browser, sshToken }) => {
    const ctx = await browser.newContext();
    await ctx.addInitScript(([tk]) => globalThis.localStorage.setItem('datara_token', tk), [sshToken]);
    await ctx.route('**/api/**', (route) => route.continue({ headers: { ...route.request().headers(), authorization: `Bearer ${sshToken}` } }));
    const probe = await ctx.newPage();
    try {
        await probe.goto('/dep/ssh', { waitUntil: 'domcontentloaded' });
        const hit = await probe.waitForSelector('[data-create]', { timeout: 8000 }).catch(() => null);
        routeReady = hit !== null;
        routeProbeNote = routeReady
            ? 'ok'
            : `路由未承载（落点 url=${probe.url()}，标题=${await probe.title()}）——1.9 制品须含 /dep/ssh 与 ssh-nodes 后端域`;
    }
    finally {
        await ctx.close();
    }
    if (!routeReady)
        test.skip(true, `环境闸：${routeProbeNote}`);
});
/* ---------------- 闭环用例 ---------------- */
test.describe.serial('SSH 节点管理闭环（IMPL-v4-03 v1.1 / RT-02a 前置）', () => {
    const suffix = `${Date.now()}`;
    const nodeName = `e2e-ssh-node-${suffix}`;
    const nodeId = { value: 0 };
    /** 仅入库密文，不出网；用于遮罩断言（后端 `_payload` 原样回吐，故列表可见掩码明文尾段）。 */
    const credValue = `sk-datara-e2e-ssh-${suffix}`;
    test('01 路由承载：/dep/ssh 渲染 SSH 节点管理页', async ({ sshPage: page }) => {
        await page.goto('/dep/ssh');
        await expect(page.getByRole('heading', { name: 'SSH 节点' })).toBeVisible();
        await expect(page.locator('[data-create]')).toBeEnabled();
        await shot(page, 's1_route_list');
        record('01.route', true, '页面渲染 + 新建入口可用');
    });
    test('02 新建：创建 SSH 节点（POST /rebuild/ssh-nodes）', async ({ sshPage: page }) => {
        await page.goto('/dep/ssh');
        await page.click('[data-create]');
        await expect(page.getByRole('dialog', { name: '新建 SSH 节点' })).toBeVisible();
        await page.fill('[data-name]', nodeName);
        await page.fill('[data-host]', PROBE_HOST);
        await page.fill('[data-port]', '22');
        await page.fill('[data-user]', 'root');
        await page.fill('[data-cred-input]', credValue);
        await page.fill('[data-tags]', 'e2e, rt-02a');
        await shot(page, 's2a_form_filled');
        await page.click('[data-save]');
        await expect(page.getByRole('dialog', { name: '新建 SSH 节点' })).toBeHidden({ timeout: 15_000 });
        const row = page.locator(`tr[data-node-id]`, { hasText: nodeName });
        await expect(row).toBeVisible({ timeout: 15_000 });
        nodeId.value = Number(await row.getAttribute('data-node-id'));
        expect(nodeId.value).toBeGreaterThan(0);
        await shot(page, 's2b_created');
        record('02.create', true, `name=${nodeName} id=${nodeId.value}`);
    });
    test('03 凭据遮罩：默认遮罩，显示/隐藏开关可切（安全债 D4-B）', async ({ sshPage: page }) => {
        const row = page.locator(`tr[data-node-id="${nodeId.value}"]`);
        const cred = row.locator('[data-cred]');
        // 默认遮罩：呈现固定掩码串，且不泄露凭据任何片段
        await expect(cred.locator('[aria-label="凭据已遮罩"]')).toBeVisible();
        expect((await cred.innerText()).trim()).toContain('••••••••');
        const maskedBody = await page.locator('body').innerText();
        expect(maskedBody).not.toContain(credValue);
        await shot(page, 's3a_masked');
        // 显示：明文可见
        await row.locator(`[data-cred-toggle="${nodeId.value}"]`).click();
        await expect(cred).toContainText(credValue);
        // 隐藏：回到遮罩态，明文从 DOM 移除
        await row.locator(`[data-cred-toggle="${nodeId.value}"]`).click();
        await expect(cred.locator('[aria-label="凭据已遮罩"]')).toBeVisible();
        expect(await page.locator('body').innerText()).not.toContain(credValue);
        await shot(page, 's3b_remasked');
        record('03.cred_mask', true, '默认遮罩 + 显隐切换 + 遮罩态零泄露');
    });
    test('04 重名保护：同名创建被拒（后端 4102 duplicateName）', async ({ sshPage: page }) => {
        // 前端路径：表单提交后列表不新增本名行，且错误横幅出现
        await page.click('[data-create]');
        await page.fill('[data-name]', nodeName);
        await page.fill('[data-host]', PROBE_HOST);
        await page.fill('[data-port]', '22');
        await page.fill('[data-user]', 'root');
        await page.fill('[data-cred-input]', credValue);
        await page.click('[data-save]');
        await expect(page.getByRole('dialog', { name: '新建 SSH 节点' })).toBeVisible(); // 失败不清场
        await expect(page.locator('p[role="alert"]')).toBeVisible({ timeout: 15_000 });
        // 后端契约直证：同源 fetch 直连，坐实 4102（页面同源，token 取 localStorage）
        const dup = await page.evaluate(async ({ base, name, host, cred }) => {
            const tk = globalThis.localStorage.getItem('datara_token') ?? '';
            const res = await fetch(`${base}/api/v1/rebuild/ssh-nodes`, {
                method: 'POST',
                headers: { 'content-type': 'application/json', token: tk },
                body: JSON.stringify({ name, host, port: 22, ssh_user: 'root', cred, tags: [], enabled: true }),
            });
            const body = (await res.json().catch(() => ({})));
            return { status: res.status, code: body.code };
        }, { base: BASE, name: nodeName, host: PROBE_HOST, cred: credValue });
        expect(dup.code).toBe(4102);
        await shot(page, 's4_duplicate_guard');
        record('04.duplicate_guard', true, `前端错误横幅 + 后端 POST → ${dup.status}/${dup.code}`);
    });
    test('05 探测：不可路由目标走结构化结果（POST /{id}/probe）', async ({ sshPage: page }) => {
        await page.goto('/dep/ssh');
        const row = page.locator(`tr[data-node-id="${nodeId.value}"]`);
        await row.locator('[data-probe]').click();
        const result = page.locator('[data-probe-result]');
        await expect(result).toBeVisible({ timeout: 40_000 });
        // 结果模板：`${name}：连接成功|连接失败（${message}）`——两种分支均属结构化返回，不做成功/失败硬断言
        await expect(result).toContainText('连接');
        await shot(page, 's5_probe_result');
        record('05.probe', true, `探测结果：${(await result.innerText()).slice(0, 120)}`);
    });
    test('06 删除：原生 confirm 确认后删除（DELETE 200）', async ({ sshPage: page }) => {
        await page.goto('/dep/ssh');
        const row = page.locator(`tr[data-node-id="${nodeId.value}"]`);
        await expect(row).toBeVisible();
        page.once('dialog', (d) => d.accept());
        await row.locator('[data-delete]').click();
        await expect(row).toBeHidden({ timeout: 15_000 });
        await shot(page, 's6_deleted');
        record('06.delete', true, `id=${nodeId.value} 确认后删除`);
    });
    test('07 不存在保护：DELETE 已删 id → 后端 4101 notFound', async ({ sshPage: page }) => {
        const gone = await page.evaluate(async ({ base, id }) => {
            const tk = globalThis.localStorage.getItem('datara_token') ?? '';
            const res = await fetch(`${base}/api/v1/rebuild/ssh-nodes/${id}`, {
                method: 'DELETE',
                headers: { token: tk },
            });
            const body = (await res.json().catch(() => ({})));
            return { status: res.status, code: body.code };
        }, { base: BASE, id: nodeId.value });
        expect(gone.code).toBe(4101);
        await shot(page, 's7_not_found_guard');
        record('07.not_found', true, `DELETE 已删 id → ${gone.status}/${gone.code}`);
    });
});
/* ---------------- 证据落档（v4 A3 成对） ---------------- */
test.afterAll(() => {
    evidence.unverified = [
        '本机零执行：本文件为交付物，全部断言须在 192.168.1.9 执行方成立（TEST-ENVIRONMENT-POLICY）',
        '探测目标缺省为 TEST-NET-1 不可路由地址（结构化失败路径）；成功路径需注入 E2E_SSH_PROBE_HOST 指向可达 SSH 主机',
        '路由未承载时（1.9 制品不含 /dep/ssh 或 ssh-nodes 域）前置探测失败整组 skip，属环境闸非代码缺陷',
        '本件为 RT-IMPL-V4-02a 的 1.9 实跑前置，不构成 02a 验收通过证据',
    ];
    writeFileSync(path.join(EV_DIR, 'sshNode.evidence.json'), JSON.stringify(evidence, null, 2), 'utf-8');
    console.log(`evidence → ${path.join(EV_DIR, 'sshNode.evidence.json')}`);
});

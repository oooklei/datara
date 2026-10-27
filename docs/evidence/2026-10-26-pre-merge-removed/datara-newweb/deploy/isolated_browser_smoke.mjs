import { chromium } from '@playwright/test';

const base = process.env.DATARA_WEB_BASE || 'http://192.168.1.9:18101';
const token = process.env.DATARA_TEST_TOKEN || '';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
if (token) await page.addInitScript((value) => { window.__DATARA_TEST_TOKEN__ = value; }, token);
const routes = ['/', '/dag', '/ide', '/p/1/resources', '/p/1/ide', '/p/1/dep', '/open/key', '/open/api', '/open/llm'];
const result = {};
for (const route of routes) {
  const response = await page.goto(base + route, { waitUntil: 'domcontentloaded', timeout: 20000 });
  result[route] = { status: response?.status() ?? 0, title: await page.title(), body: (await page.locator('body').innerText()).slice(0, 160) };
}
console.log(JSON.stringify({ base, routes: result }, null, 2));
await browser.close();

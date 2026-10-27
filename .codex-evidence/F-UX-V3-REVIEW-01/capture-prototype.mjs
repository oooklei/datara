import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire('D:/需求/数据治理工具/Datara/datara-newweb/package.json')
const { chromium } = require('playwright')

const out = 'D:/需求/数据治理工具/Datara/.codex-evidence/F-UX-V3-REVIEW-01'
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } })
const errors = []
page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()) })
page.on('pageerror', err => errors.push(err.message))
await page.goto('file:///D:/super-develop/datara-ux-prototype.html', { waitUntil: 'load' })
await page.waitForTimeout(1000)
await page.screenshot({ path: path.join(out, 'prototype-dashboard.png'), fullPage: true })

for (const [label, file] of [
  ['工作流定义与编排', 'prototype-dag.png'],
  ['SQL IDE', 'prototype-ide.png'],
]) {
  await page.getByText(label, { exact: true }).first().click()
  await page.waitForTimeout(200)
  await page.screenshot({ path: path.join(out, file), fullPage: true })
}

const buttons = await page.locator('button').allTextContents()
const links = await page.locator('a').allTextContents()
const visibleViews = await page.locator('.view.on').count()
const mobile = await browser.newPage({ viewport: { width: 375, height: 812 } })
await mobile.goto('file:///D:/super-develop/datara-ux-prototype.html', { waitUntil: 'load' })
await mobile.waitForTimeout(500)
await mobile.screenshot({ path: path.join(out, 'prototype-mobile.png'), fullPage: true })
const overflowX = await mobile.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
console.log(JSON.stringify({ title: await page.title(), buttons: buttons.length, links: links.length, visibleViews, errors, mobileOverflowX: overflowX }))
await browser.close()

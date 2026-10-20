#!/usr/bin/env node
/**
 * FE-04 扩展（演示）组 demo 标识摘除 — 双向核验脚本
 *
 * 核验两个方向：
 *   1. 源码核验：对每个已登记摘除项，确认 routes.ts / App.vue 中无残留 demo 标识
 *   2. 引用核验：确认对应页面组件无 services/mock/seed.ts 误引用
 *   3. build 核验：可选执行 npm run build 确认无悬空引用
 *
 * 用法：
 *   node scripts/verify-demo-removal.mjs           # 核验已登记项
 *   node scripts/verify-demo-removal.mjs --build   # 额外执行 build 核验
 *
 * 依据：WBS FE-04；设计 §10 豁免注记 D-1。
 */
import { readFileSync, existsSync } from 'node:fs'
import { execSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = join(__dirname, '..')

// ---- 登记摘除清单（与 src/views/DEMO_FLAG_REMOVAL.md 同步） ----
// status: 'pending' = 待批次执行；'done' = 已摘除（核验应通过）
const REMOVAL_LIST = [
  // 第 5 批（STREAM 域，FE-10 触发）
  { route: '/stream/list', domain: 'STREAM', batch: 5, file: 'src/views/stream/StreamListView.vue', status: 'pending' },
  { route: '/stream/detail/:id', domain: 'STREAM', batch: 5, file: 'src/views/stream/StreamDetailView.vue', status: 'pending' },
]

let failures = 0
let passes = 0

function ok(msg) { passes++; console.log(`  PASS  ${msg}`) }
function fail(msg) { failures++; console.error(`  FAIL  ${msg}`) }

// ---- 1. 源码核验：routes.ts / App.vue 中 demo 标识残留 ----
function verifyNoDemoFlag() {
  console.log('\n[1] 源码核验：routes.ts / App.vue 中 demo 标识残留')
  const routesSrc = readFileSync(join(ROOT, 'src/router/routes.ts'), 'utf8')
  const appSrc = readFileSync(join(ROOT, 'src/App.vue'), 'utf8')

  for (const item of REMOVAL_LIST) {
    if (item.status !== 'done') {
      console.log(`  SKIP  ${item.route}（批次 ${item.batch} 未执行摘除）`)
      continue
    }
    // 在 routes.ts 中查找该路由行，确认无 demo: true
    const routeLine = routesSrc.split('\n').find((l) => l.includes(`path: '${item.route}'`))
    if (routeLine && /demo:\s*true/.test(routeLine)) {
      fail(`${item.route} routes.ts 仍有 demo: true`)
    } else if (routeLine) {
      ok(`${item.route} routes.ts 无 demo 标识`)
    } else {
      fail(`${item.route} routes.ts 未找到路由行`)
    }
    // App.vue 菜单面：确认该路由 path 不出现在扩展（演示）组菜单项中
    const menuLine = appSrc.split('\n').find((l) => l.includes(`path: '${item.route}'`))
    if (menuLine) {
      // 检查该行是否在扩展（演示）组内（向上查找 group: '扩展（演示）'）
      const lines = appSrc.split('\n')
      const idx = lines.indexOf(menuLine)
      const nearby = lines.slice(Math.max(0, idx - 20), idx).join('\n')
      if (nearby.includes("group: '扩展（演示）'")) {
        fail(`${item.route} 仍在扩展（演示）组菜单中`)
      } else {
        ok(`${item.route} 不在扩展（演示）组菜单`)
      }
    } else {
      ok(`${item.route} App.vue 菜单无此项（已摘除或本无菜单项）`)
    }
  }
}

// ---- 2. 引用核验：页面组件无 services/mock/seed.ts 误引用 ----
function verifyNoSeedReference() {
  console.log('\n[2] 引用核验：页面组件无 services/mock/seed.ts 误引用')
  for (const item of REMOVAL_LIST) {
    if (item.status !== 'done') {
      console.log(`  SKIP  ${item.file}（批次 ${item.batch} 未执行摘除）`)
      continue
    }
    const filePath = join(ROOT, item.file)
    if (!existsSync(filePath)) {
      fail(`${item.file} 文件不存在`)
      continue
    }
    const src = readFileSync(filePath, 'utf8')
    // 检查是否引用 services/mock/seed（相对路径变体）
    const seedPatterns = [
      new RegExp('services/mock/seed'),
      new RegExp('mock/seed'),
      new RegExp('seedWorkflows|listSeedTaskDocs|newWorkflowDoc'),
    ]
    const hasSeedRef = seedPatterns.some((p) => p.test(src))
    if (hasSeedRef) {
      fail(`${item.file} 仍引用 services/mock/seed`)
    } else {
      ok(`${item.file} 无 seed.ts 引用`)
    }
  }
}

// ---- 3. build 核验（可选） ----
function verifyBuild() {
  console.log('\n[3] build 核验：npm run build')
  try {
    execSync('npm run build', { cwd: ROOT, stdio: 'pipe', timeout: 120000 })
    ok('build 通过')
  } catch (e) {
    fail(`build 失败: ${e.message}`)
  }
}

// ---- 主流程 ----
console.log('FE-04 demo 标识摘除 — 双向核验')
console.log(`登记摘除项: ${REMOVAL_LIST.length} 条（done=${REMOVAL_LIST.filter((i) => i.status === 'done').length}, pending=${REMOVAL_LIST.filter((i) => i.status === 'pending').length}）`)

verifyNoDemoFlag()
verifyNoSeedReference()

const withBuild = process.argv.includes('--build')
if (withBuild) {
  verifyBuild()
} else {
  console.log('\n[3] build 核验：跳过（传 --build 启用）')
}

console.log(`\n结果: ${passes} passed, ${failures} failed`)
process.exit(failures > 0 ? 1 : 0)

/**
 * 服务层 import 契约守卫（回归防护）
 *
 * 起因（2026-09-27 代码审计）：ComponentDesignView.vue 调用 getImpactedWorkflows
 * 却漏写 import，运行时抛 ReferenceError。该错误被同函数内的 catch 吞掉仅弹 toast，
 * 而既有 D3 用例无一触发 release tab —— 分支从未执行，264 个用例全绿仍漏检。
 * 单测的模块 mock 会提供该符号，因此也无法暴露问题。
 *
 * 本守卫在静态层拦这类缺陷：SFC 中「调用了服务层导出函数」时，该函数名必须出现在
 * 同文件的具名 import 集合中（或在文件内本地声明以排除同名遮蔽）。与运行期行为无关，
 * 因此不会被 mock / catch / 未覆盖分支绕过。
 *
 * 补位价值：vue-tsc 能报 TS2304，但若该错误被类型断言或 any 掩盖，本守卫仍独立生效。
 */
import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(HERE, '..')
const SERVICES = join(SRC, 'services')

/** 服务层模块的函数导出名（只收 function/async function——「被调用」只可能来自函数） */
function functionExports(file: string): string[] {
  const src = readFileSync(file, 'utf8')
  const names = new Set<string>()
  for (const m of src.matchAll(/export\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/g)) {
    names.add(m[1])
  }
  return [...names]
}

/** 展开 barrel 的具名再导出（`export { a, b } from './x'`），`export *` 递归展开 */
function reexportedFunctions(file: string, seen = new Set<string>()): string[] {
  const src = readFileSync(file, 'utf8')
  const out: string[] = []
  for (const m of src.matchAll(/export\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g)) {
    for (const part of m[1].split(',')) {
      const name = part.trim().replace(/^type\s+/, '').split(/\s+as\s+/)[0].trim()
      if (name) out.push(name)
    }
  }
  for (const m of src.matchAll(/export\s*\*\s*from\s*['"]([^'"]+)['"]/g)) {
    const target = resolve(dirname(file), m[1])
    if (existsSync(target) && !seen.has(target)) {
      seen.add(target)
      out.push(...functionExports(target), ...reexportedFunctions(target, seen))
    }
  }
  return out
}

function allServiceFunctions(): Set<string> {
  const names = new Set<string>()
  for (const f of readdirSync(SERVICES)) {
    if (!f.endsWith('.ts') || f.endsWith('.d.ts')) continue
    const file = join(SERVICES, f)
    functionExports(file).forEach((n) => names.add(n))
    reexportedFunctions(file).forEach((n) => names.add(n))
  }
  return names
}

function walkVue(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name)
    if (e.isDirectory()) {
      if (e.name !== '__tests__' && e.name !== 'node_modules') walkVue(p, out)
    } else if (e.name.endsWith('.vue')) {
      out.push(p)
    }
  }
  return out
}

/** 某 SFC 的具名 import 名字集合（跨所有来源，够用：同名遮蔽由本地声明豁免兜底） */
function namedImports(src: string): Set<string> {
  const names = new Set<string>()
  for (const m of src.matchAll(/import\s*\{([\s\S]*?)\}\s*from\s*['"][^'"]+['"]/g)) {
    for (const part of m[1].split(',')) {
      const name = part.trim().replace(/^type\s+/, '').split(/\s+as\s+/).pop()!.trim()
      if (name) names.add(name)
    }
  }
  return names
}

/** 排除同名遮蔽：文件内本地声明了该函数（function/const/let/var） */
function locallyDeclared(src: string, name: string): boolean {
  const re = new RegExp(
    String.raw`(?:function\s+${name}\b|(?:const|let|var)\s+${name}\b)`,
  )
  return re.test(src)
}

describe('服务层 import 契约', () => {
  const serviceFns = allServiceFunctions()

  it('已收集到服务层函数导出（守卫自身有效，非空集）', () => {
    expect(serviceFns.size).toBeGreaterThan(0)
    expect(serviceFns.has('getImpactedWorkflows')).toBe(true)
  })

  it('SFC 调用服务层函数时必须具名 import 该函数', () => {
    const violations: string[] = []
    for (const file of walkVue(SRC)) {
      const src = readFileSync(file, 'utf8')
      const imported = namedImports(src)
      for (const name of serviceFns) {
        // 调用形态：name(  —— 排除属性访问 obj.name( 与字符串/注释噪声
        const called = new RegExp(String.raw`(^|[^.\w$])${name}\s*\(`).test(src)
        if (!called) continue
        if (imported.has(name) || locallyDeclared(src, name)) continue
        violations.push(`${file.replace(SRC + '\\', '')}: 调用 ${name}() 但未 import`)
      }
    }
    expect(violations).toEqual([])
  })
})

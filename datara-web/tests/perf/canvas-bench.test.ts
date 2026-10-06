/**
 * canvas-bench（方案 §3.6 / §11.3）：200 节点/400 边标准图的纯前端指标基准。
 * 运行方式：npm run bench:canvas（vitest --root tests/perf——vitest 5 的 --dir 不会
 * 改写主配置的 include 基准、CLI 亦无 --include 覆盖项，故改用 --root 让 vitest
 * 按默认 include 在 tests/perf 下收集 *.test.ts；主套件只收集 src 目录下的
 * *.test.ts，本目录不会被日常 vitest run 收集）。
 * - cloneDoc×100 / undo 快照（structuredClone）×50 计时进本脚本；
 * - FPS 类渲染指标属浏览器行为，留浏览器手动验证，不进本脚本；
 * - 每次运行把基线写入 tests/perf/last-bench.json，供后续批次改动对比（§11.3）。
 */
import { afterAll, describe, expect, it } from 'vitest'
import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { cloneDoc, type GraphDocument } from '../../src/graph/model'
import { buildBenchDoc } from './buildBenchDoc'

const perfDir = dirname(fileURLToPath(import.meta.url))
// 两个计时结果在 it 内回填；afterAll 中两者均已量测才落盘，避免记录残缺基线
let cloneDoc100Ms: number | undefined
let undoSnapshot50Ms: number | undefined

describe('canvas-bench（方案§3.6 基准，200 节点/400 边）', () => {
  const doc: GraphDocument = buildBenchDoc(200, 400)

  it('结构：恰好 200 节点 / 400 边（链式 + 汇聚补足）', () => {
    expect(doc.nodes.length).toBe(200)
    expect(doc.edges.length).toBe(400)
  })

  it('cloneDoc×100 < 1500ms', () => {
    const t0 = performance.now()
    for (let i = 0; i < 100; i++) cloneDoc(doc)
    const cost = performance.now() - t0
    cloneDoc100Ms = cost
    expect(cost).toBeLessThan(1500)
  })

  it('undo 快照（structuredClone）×50 < 1000ms', () => {
    const t0 = performance.now()
    for (let i = 0; i < 50; i++) structuredClone(doc)
    const cost = performance.now() - t0
    undoSnapshot50Ms = cost
    expect(cost).toBeLessThan(1000)
  })

  afterAll(() => {
    if (cloneDoc100Ms === undefined || undoSnapshot50Ms === undefined) return
    const baseline = {
      generatedAt: new Date().toISOString(),
      nodeCount: doc.nodes.length,
      edgeCount: doc.edges.length,
      cloneDoc100Ms: Math.round(cloneDoc100Ms * 100) / 100,
      undoSnapshot50Ms: Math.round(undoSnapshot50Ms * 100) / 100,
    }
    writeFileSync(join(perfDir, 'last-bench.json'), `${JSON.stringify(baseline, null, 2)}\n`)
  })
})

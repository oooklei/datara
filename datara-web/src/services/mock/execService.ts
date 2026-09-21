/**
 * execService mock：提交执行立即返回 runId（显示/运行分离），
 * 用定时器按拓扑序派发 node:status 事件模拟异步执行。
 * 真实后端阶段：run 换为 REST 调用，状态推送换为 WebSocket，事件结构不变。
 */
import type { GraphDocument } from '../../graph/model'
import { topoSort } from '../../graph/model'
import type { IExecService, RunHandle, RunOptions } from '../types'
import { bus } from '../eventBus'

interface RunCtx {
  timers: ReturnType<typeof setTimeout>[]
  stopped: boolean
}

const runs = new Map<string, RunCtx>()
let runSeq = 0

/** 可达子图（从 fromNode 出发），未指定则全图 */
function reachable(doc: GraphDocument, from?: string): Set<string> {
  if (!from) return new Set(doc.nodes.map((n) => n.id))
  const adj = new Map<string, string[]>()
  doc.nodes.forEach((n) => adj.set(n.id, []))
  doc.edges.forEach((e) => adj.get(e.source)?.push(e.target))
  const seen = new Set<string>([from])
  const q = [from]
  while (q.length) {
    const cur = q.shift()!
    ;(adj.get(cur) ?? []).forEach((t) => {
      if (!seen.has(t)) { seen.add(t); q.push(t) }
    })
  }
  return seen
}

export const execService: IExecService = {
  async run(doc, opts: RunOptions = {}): Promise<RunHandle> {
    runSeq += 1
    const runId = `R${Date.now().toString(36)}${runSeq}`
    const scope = reachable(doc, opts.fromNode)
    const { order } = topoSort(doc)
    const queue = order.filter((id) => scope.has(id))
    const ctx: RunCtx = { timers: [], stopped: false }
    runs.set(runId, ctx)

    bus.emit('run:start', { runId, total: queue.length })

    let t = 300
    queue.forEach((nodeId) => {
      ctx.timers.push(setTimeout(() => {
        if (ctx.stopped) return
        bus.emit('run:node', { runId, nodeId, status: 'running', ts: Date.now() })
        // 节点执行耗时（mock 600-900ms），并保留 8% 失败率演示失败链路
        const cost = 600 + Math.floor(Math.random() * 300)
        ctx.timers.push(setTimeout(() => {
          if (ctx.stopped) return
          const fail = Math.random() < 0.08
          bus.emit('run:node', {
            runId, nodeId, ts: Date.now(),
            status: fail ? 'fail' : 'success',
            log: fail ? 'exit code 1 · 模拟执行失败' : 'exit code 0',
          })
          if (fail) {
            // 失败后剩余节点保持 queued 并结束本次运行（清理挂起定时器与运行上下文，防泄漏）
            ctx.stopped = true
            ctx.timers.forEach(clearTimeout)
            runs.delete(runId)
            bus.emit('run:end', { runId, result: 'fail' })
          }
        }, cost))
      }, t))
      t += 1000
    })

    ctx.timers.push(setTimeout(() => {
      runs.delete(runId)
      if (!ctx.stopped) {
        ctx.stopped = true
        bus.emit('run:end', { runId, result: 'success' })
      }
    }, t + 1200))

    return { runId }
  },

  async stop(runId) {
    const ctx = runs.get(runId)
    if (!ctx) return
    ctx.timers.forEach(clearTimeout)
    ctx.stopped = true
    runs.delete(runId)
    bus.emit('run:end', { runId, result: 'stopped' })
  },
}

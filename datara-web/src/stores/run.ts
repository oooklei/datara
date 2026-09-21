import { defineStore } from 'pinia'
import type { GraphDocument, GNode } from '../graph/model'
import type { NodeRunStatus, RunOptions } from '../services/types'
import { execService } from '../services/mock/execService'
import { bus } from '../services/eventBus'

export const useRunStore = defineStore('run', {
  state: () => ({
    runId: '',
    running: false,
    result: '' as '' | 'success' | 'fail' | 'stopped',
    /** 节点运行状态（key=节点 id）：NodeRunStatus | I3 实例染色的 'kill'/'skip' 等（DataNode 按 st- 前缀渲染） */
    nodeStatus: {} as Record<string, string>,
    logs: [] as { ts: number; text: string; cls: string }[],
  }),
  actions: {
    reset() {
      this.runId = ''
      this.running = false
      this.result = ''
      this.nodeStatus = {}
      this.logs = []
    },
    log(text: string, cls = '') {
      this.logs.push({ ts: Date.now(), text, cls })
      if (this.logs.length > 200) this.logs.splice(0, this.logs.length - 200)
    },
    async start(doc: GraphDocument, opts?: RunOptions) {
      if (this.running) return
      this.reset()
      const onNode = (p: unknown) => {
        const ev = p as { runId: string; nodeId: string; status: NodeRunStatus; log?: string }
        if (ev.runId !== this.runId) return
        this.nodeStatus[ev.nodeId] = ev.status
        const name = doc.nodes.find((n) => n.id === ev.nodeId)?.data.name ?? ev.nodeId
        this.log(`[${ev.status}] ${name}${ev.log ? ' · ' + ev.log : ''}`, ev.status === 'success' ? 'ok' : ev.status === 'fail' ? 'fail' : '')
      }
      const onEnd = (p: unknown) => {
        const ev = p as { runId: string; result: string }
        if (ev.runId !== this.runId) return
        this.running = false
        this.result = ev.result as typeof this.result
        this.log(`运行结束 · ${ev.result}`, ev.result === 'success' ? 'ok' : 'fail')
        bus.off('run:node', onNode)
        bus.off('run:end', onEnd)
      }
      bus.on('run:node', onNode)
      bus.on('run:end', onEnd)
      const { runId } = await execService.run(doc, opts)
      this.runId = runId
      this.running = true
      this.log(`提交运行 ${runId}（显示/运行分离：提交即返回，状态异步推送）`)
    },
    async stop() {
      if (!this.runId) return
      await execService.stop(this.runId)
    },
    statusOf(node: GNode): NodeRunStatus | 'idle' {
      // nodeStatus 已放宽为 Record<string, string>（容纳 I3 引擎染色 kill/skip 等）；mock 链路写入恒为 NodeRunStatus
      return (this.nodeStatus[node.id] as NodeRunStatus | undefined) ?? 'idle'
    },
  },
})

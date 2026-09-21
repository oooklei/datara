/**
 * EventBus：mock 阶段模拟 WebSocket 推送通道。
 * 真实后端落地时，仅把 emit 来源替换为 WS 消息，事件名与负载结构不变（显示/运行分离契约）。
 */
export type BusHandler = (payload: unknown) => void

const handlers = new Map<string, Set<BusHandler>>()

export const bus = {
  on(event: string, fn: BusHandler): void {
    if (!handlers.has(event)) handlers.set(event, new Set())
    handlers.get(event)!.add(fn)
  },
  off(event: string, fn: BusHandler): void {
    handlers.get(event)?.delete(fn)
  },
  emit(event: string, payload?: unknown): void {
    // 单个 handler 异常不阻断其余订阅者（错误隔离）
    handlers.get(event)?.forEach((fn) => {
      try {
        fn(payload)
      } catch (err) {
        console.error(`[bus] handler error on "${event}"`, err)
      }
    })
  },
}

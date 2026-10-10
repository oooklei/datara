import { buildInstanceStreamUrl } from './graphApi'
import type { NodeRunEvent } from '../stores/run'

/**
 * Single-run node-event subscription.  Native EventSource remembers the most
 * recent SSE `id`, so reconnects send Last-Event-ID and the server replays the
 * missing durable events before live delivery resumes.
 */
export function openRunEventSource(
  instanceId: string,
  onEvent: (event: NodeRunEvent) => void,
  onError?: () => void,
): EventSource {
  /* 非浏览器运行环境（Node 测试环境无原生 EventSource）不建立订阅：
     返回空操作句柄保证调用链不中断（close 可安全调用、不污染订阅链路）。 */
  if (typeof EventSource === 'undefined') {
    onError?.()
    return { close() {} } as unknown as EventSource
  }
  const source = new EventSource(buildInstanceStreamUrl(instanceId))
  source.addEventListener('node_event', (raw) => {
    try {
      onEvent(JSON.parse((raw as MessageEvent).data) as NodeRunEvent)
    } catch {
      // A malformed event must not take down the browser's reconnect loop.
    }
  })
  source.onerror = () => onError?.()
  return source
}

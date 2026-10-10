/**
 * §0.3 sseSource 门控（runStore.subscribeNodeEvents）单元测试。
 * 关键钉死（默认路径）：polling（默认）不开 node_event SSE——runId 仍置位，
 * 既有轮询/实例流/总线通道维持现状（防回归）；pubsub 才真正启用 openRunEventSource
 * （Task 18 runStore 唯一持连方），事件回调直入 applyNodeEvent 染色；
 * 重复订阅先关旧连接；stopNodeEvents 关闭当前连接。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const openSpy = vi.hoisted(() =>
  vi.fn((_instanceId: string, _onEvent: (ev: unknown) => void) => ({ close: vi.fn() })))

vi.mock('../../services/runEventSource', () => ({
  openRunEventSource: openSpy,
}))

import { useRunStore } from '../run'
import { setFlags } from '../../services/featureFlags'

/** node 环境无 localStorage：桩内存存储让 setFlags 落盘生效 */
function stubFlagsStorage(): void {
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v) },
  })
}

describe('§0.3 sseSource 门控（runStore node_event 订阅）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    openSpy.mockClear()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('默认 polling：subscribeNodeEvents 不开 SSE，runId 仍置位（默认路径钉死）', () => {
    const run = useRunStore()
    run.subscribeNodeEvents('r1')
    expect(openSpy).not.toHaveBeenCalled()
    expect(run.runId).toBe('r1')
    expect(() => run.stopNodeEvents()).not.toThrow()
  })

  it('pubsub：真正开启 SSE 连接，事件回调直入 applyNodeEvent 染色', () => {
    stubFlagsStorage()
    setFlags({ sseSource: 'pubsub' })
    const run = useRunStore()
    run.subscribeNodeEvents('r1')
    expect(openSpy).toHaveBeenCalledTimes(1)
    expect(openSpy.mock.calls[0]![0]).toBe('r1')
    const onEvent = openSpy.mock.calls[0]![1]
    onEvent({ runId: 'r1', nodeId: 'n1', type: 'node_executing', ts: 1 })
    expect(run.nodeStateMap.n1).toMatchObject({ state: 'executing', color: 'amber' })
  })

  it('pubsub 重复订阅：先关旧连接再开新连接', () => {
    stubFlagsStorage()
    setFlags({ sseSource: 'pubsub' })
    const run = useRunStore()
    run.subscribeNodeEvents('r1')
    run.subscribeNodeEvents('r2')
    expect(openSpy).toHaveBeenCalledTimes(2)
    const first = openSpy.mock.results[0]!.value
    expect(first.close).toHaveBeenCalledTimes(1)
  })

  it('stopNodeEvents 关闭当前连接', () => {
    stubFlagsStorage()
    setFlags({ sseSource: 'pubsub' })
    const run = useRunStore()
    run.subscribeNodeEvents('r1')
    const handle = openSpy.mock.results[0]!.value
    run.stopNodeEvents()
    expect(handle.close).toHaveBeenCalledTimes(1)
  })
})

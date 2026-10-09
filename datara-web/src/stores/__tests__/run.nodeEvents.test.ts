import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useRunStore } from '../run'

describe('runStore node_event consumption', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('maps the four canvas states', () => {
    const store = useRunStore()
    store.applyNodeEvent({ runId: 'r1', nodeId: 'n1', type: 'node_executing', ts: 1 })
    store.applyNodeEvent({ runId: 'r1', nodeId: 'n2', type: 'node_executed', ts: 2 })
    store.applyNodeEvent({ runId: 'r1', nodeId: 'n3', type: 'node_cached', ts: 3 })
    store.applyNodeEvent({ runId: 'r1', nodeId: 'n4', type: 'node_error', ts: 4, payload: { message: 'x' } })

    expect(store.nodeStateMap.n1).toMatchObject({ state: 'executing', color: 'amber' })
    expect(store.nodeStateMap.n2).toMatchObject({ state: 'executed', color: 'green' })
    expect(store.nodeStateMap.n3).toMatchObject({ state: 'cached', color: 'gray' })
    expect(store.nodeStateMap.n4).toMatchObject({ state: 'error', color: 'red', message: 'x' })
  })

  it('ignores events from a different active run', () => {
    const store = useRunStore()
    store.runId = 'r1'
    store.applyNodeEvent({ runId: 'r2', nodeId: 'n1', type: 'node_executing', ts: 1 })
    expect(store.nodeStateMap.n1).toBeUndefined()
  })
})

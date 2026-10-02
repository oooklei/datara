/**
 * graphApi 契约测试（I12-D2 保存并发乐观锁）：
 * - save 请求体携带 base_version（来源 doc.version，后端 CAS 比对）
 * - 409 并发冲突（code 2005）透传错误消息与业务码（http 层挂 code，供调用方提示刷新）
 * stub fetch 方案沿用 datasourceApi.test.ts 先例。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { buildInstanceStreamUrl, realGraphService, streamInstanceEvents } from '../graphApi'
import type { GraphDocument } from '../../graph/model'
import type { InstanceStreamHandlers } from '../graphApi'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('localStorage', { getItem: () => 'tok-i12', setItem: vi.fn(), removeItem: vi.fn() })
})

function bareDoc(id: string, version: number): GraphDocument {
  return { id, name: '并发用例', version, meta: { profile: 'dag' }, nodes: [], edges: [] }
}

describe('graphApi 保存并发保护（I12-D2）', () => {
  it('save 请求体携带 base_version（= doc.version），与方法/路径对齐后端契约', async () => {
    fetchMock.mockResolvedValueOnce({ json: async () => ({ code: 0, msg: 'success', data: { version: 7 } }) })
    const doc = bareDoc('wf_cas_doc', 6)
    const r = await realGraphService.save(doc, '备注')
    expect(r.version).toBe(7)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/workflow-definitions/wf_cas_doc/save')
    expect(init.method).toBe('PUT')
    const body = JSON.parse(init.body)
    expect(body.base_version).toBe(6)
    expect(body.remark).toBe('备注')
    expect(body.doc.id).toBe('wf_cas_doc')
  })

  it('409 并发冲突（code 2005）→ reject 且错误消息透传、err.code 携带业务码', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({ code: 2005, msg: '定义已被他人更新（当前 v9，提交基于 v6），请刷新后重试', data: null }),
    })
    const err = await realGraphService.save(bareDoc('wf_cas_doc', 6)).then(
      () => {
        throw new Error('应抛出冲突错误')
      },
      (e) => e as Error & { code?: number },
    )
    expect(err.code).toBe(2005)
    expect(err.message).toContain('请刷新后重试')
  })
})

/* ================= D3：save 序列化注入 componentRef（§9.5 前端镜像） ================= */

function stubRegistry(items: { type: string; publishedVersion: number | null }[]): void {
  fetchMock.mockResolvedValueOnce({ json: async () => ({ code: 0, msg: 'success', data: { items } }) })
}

function injDoc(): GraphDocument {
  return {
    id: 'wf_inj', name: '注入用例', version: 2, meta: { profile: 'dag' }, edges: [],
    nodes: [
      { id: 'n1', type: 'user_demo', position: { x: 0, y: 0 }, data: { name: '无 ref → 注入' } },
      { id: 'sys_exec_9', type: 'user_demo', position: { x: 1, y: 1 }, data: { name: '物化产物 → 豁免' } },
      { id: 'n3', type: 'user_demo', position: { x: 2, y: 2 }, data: { name: '已有 ref → 不动', componentRef: { type: 'user_demo', version: 1 } } },
      { id: 'n4', type: 'other_type', position: { x: 3, y: 3 }, data: { name: 'registry 外 → 不注入' } },
    ],
  }
}

describe('graphApi save 注入 componentRef（D3 §9.5）', () => {
  it('无 ref 节点注入 registry published 版本；sys_exec_ 豁免；已有 ref 幂等不动；registry 外类型不注入', async () => {
    stubRegistry([{ type: 'user_demo', publishedVersion: 2 }, { type: 'other_type', publishedVersion: null }])
    fetchMock.mockResolvedValueOnce({ json: async () => ({ code: 0, msg: 'success', data: { version: 3 } }) })
    const doc = injDoc()
    const r = await realGraphService.save(doc)
    expect(r.version).toBe(3)
    // 先 GET registry 再 PUT save（calls[0]/calls[1]）
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/components/registry')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/workflow-definitions/wf_inj/save')
    const nodes = JSON.parse(fetchMock.mock.calls[1][1].body).doc.nodes
    expect(nodes[0].data.componentRef).toEqual({ type: 'user_demo', version: 2 })
    expect(nodes[1].data.componentRef).toBeUndefined() // sys_exec_ 豁免
    expect(nodes[2].data.componentRef).toEqual({ type: 'user_demo', version: 1 }) // 幂等：v1 不改写
    expect(nodes[3].data.componentRef).toBeUndefined() // published=null 不注入
  })

  it('未发布组件（published null）不注入；registry 拉取失败静默跳过注入，不阻断保存', async () => {
    stubRegistry([{ type: 'user_demo', publishedVersion: null }])
    fetchMock.mockResolvedValueOnce({ json: async () => ({ code: 0, msg: 'success', data: { version: 3 } }) })
    const doc = injDoc()
    await realGraphService.save(doc)
    let nodes = JSON.parse(fetchMock.mock.calls[1][1].body).doc.nodes
    expect(nodes[0].data.componentRef).toBeUndefined()

    fetchMock.mockReset()
    fetchMock.mockRejectedValueOnce(new Error('registry 端点不可达')) // registry 拉取失败
    fetchMock.mockResolvedValueOnce({ json: async () => ({ code: 0, msg: 'success', data: { version: 4 } }) })
    const r = await realGraphService.save(injDoc())
    expect(r.version).toBe(4) // 保存不受影响（R6 宽松模式后端兜底）
    nodes = JSON.parse(fetchMock.mock.calls[1][1].body).doc.nodes
    expect(nodes[0].data.componentRef).toBeUndefined()
  })

  it('nodes 为空时不发 registry 请求（早退，存量调用零开销）', async () => {
    fetchMock.mockResolvedValueOnce({ json: async () => ({ code: 0, msg: 'success', data: { version: 7 } }) })
    await realGraphService.save(bareDoc('wf_empty', 6))
    expect(fetchMock.mock.calls).toHaveLength(1)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/workflow-definitions/wf_empty/save')
  })
})

/* ================= E1：实例状态 SSE 流（streamInstanceEvents） ================= */

/** EventSource 桩：捕获订阅与 handler，emit 直发（node 环境无 EventSource） */
class FakeEventSource {
  static last: FakeEventSource | null = null
  url: string
  closed = false
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  private listeners: Record<string, (ev: MessageEvent) => void> = {}
  constructor(url: string) {
    this.url = url
    FakeEventSource.last = this
  }
  addEventListener(type: string, fn: (ev: MessageEvent) => void) { this.listeners[type] = fn }
  close() { this.closed = true }
  emit(type: string, data: unknown) { this.listeners[type]?.({ data: typeof data === 'string' ? data : JSON.stringify(data) } as MessageEvent) }
}

describe('graphApi 实例状态流（E1）', () => {
  it('订阅地址走 ?token= query（EventSource 无法带 header，api/auth 兜底口径）', () => {
    expect(buildInstanceStreamUrl('i-1')).toBe('/api/v1/instances/i-1/stream?token=tok-i12')
  })

  it('task_state_changed/instance_finished 事件解析载荷并转发 handler', () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    const got: { task?: unknown; fin?: unknown; opened?: boolean } = {}
    const h: InstanceStreamHandlers = {
      onOpen: () => { got.opened = true },
      onTaskChanged: (e) => { got.task = e },
      onFinished: (e) => { got.fin = e },
    }
    streamInstanceEvents('i-9', h)
    const es = FakeEventSource.last!
    expect(es.url).toBe('/api/v1/instances/i-9/stream?token=tok-i12')
    es.onopen?.()
    es.emit('task_state_changed', { taskId: 11, nodeId: 'n1', state: 'success', attempt: 2, loopIter: 0 })
    es.emit('instance_finished', { instanceId: 'i-9', state: 'success', endTime: null })
    expect(got.opened).toBe(true)
    expect(got.task).toMatchObject({ taskId: 11, nodeId: 'n1', state: 'success', attempt: 2 })
    expect(got.fin).toMatchObject({ instanceId: 'i-9', state: 'success' })
  })

  it('脏 JSON 载荷静默忽略不抛错；onerror 透传；句柄可 close（调用方及时释放）', () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    let errored = 0
    let taskCalls = 0
    const handle = streamInstanceEvents('i-9', {
      onTaskChanged: () => { taskCalls++ },
      onError: () => { errored++ },
    })
    const es = FakeEventSource.last!
    es.emit('task_state_changed', '{not-json') // 脏载荷
    expect(taskCalls).toBe(0)
    es.emit('task_state_changed', { taskId: 1 })
    expect(taskCalls).toBe(1)
    es.onerror?.()
    expect(errored).toBe(1)
    handle.close()
    expect(es.closed).toBe(true)
  })
})

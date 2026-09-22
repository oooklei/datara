/**
 * graphApi 契约测试（I12-D2 保存并发乐观锁）：
 * - save 请求体携带 base_version（来源 doc.version，后端 CAS 比对）
 * - 409 并发冲突（code 2005）透传错误消息与业务码（http 层挂 code，供调用方提示刷新）
 * stub fetch 方案沿用 datasourceApi.test.ts 先例。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { realGraphService } from '../graphApi'
import type { GraphDocument } from '../../graph/model'
import { TOKEN_KEY } from '../http'

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

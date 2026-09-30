/**
 * saveDraft 请求体契约测试（R1 修复回归）：
 * 后端 pydantic 模型 BaselineDraftBody 要求 snake_case（draft_rev），
 * 前端曾发驼峰 draftRev → 422（响应体无 code 字段）→ http 兜底文案
 * 拼出 "code=undefined"。本测试锁定请求体字段名，防止回归。
 * 同时锁定修订轮次端点（redraft / discard_draft）的 URL 与请求体契约。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const putSpy = vi.hoisted(() => vi.fn())
const postSpy = vi.hoisted(() => vi.fn())
vi.mock('../http', () => ({
  http: { get: vi.fn(), put: putSpy, post: postSpy },
}))
vi.mock('../apiMode', () => ({ isMock: false }))

import { saveDraft, redraftBaseline, discardBaselineRevision } from '../baselineApi'

describe('saveDraft 请求体契约（后端 BaselineDraftBody 要求 snake_case）', () => {
  beforeEach(() => {
    putSpy.mockReset().mockResolvedValue({ draftRev: 2, specHash: 'abc', status: 'designing' })
  })

  it('发送 draft_rev（下划线）而非 draftRev', async () => {
    await saveDraft('sql', { draftRev: 1, spec: { fields: [] } })
    expect(putSpy).toHaveBeenCalledTimes(1)
    const body = putSpy.mock.calls[0][1] as Record<string, unknown>
    expect(body).toHaveProperty('draft_rev', 1)
    expect(body).not.toHaveProperty('draftRev')
    expect(body).toHaveProperty('spec')
  })

  it('remark 传入时透传', async () => {
    await saveDraft('sql', { draftRev: 1, spec: {}, remark: 'r1' })
    const body = putSpy.mock.calls[0][1] as Record<string, unknown>
    expect(body).toHaveProperty('remark', 'r1')
  })
})

describe('修订轮次 API 契约（路由 /{type}/baseline/ 风格）', () => {
  beforeEach(() => {
    postSpy.mockReset().mockResolvedValue({ draftRev: 2, status: 'designing', fromVersion: 1, specHash: 'h' })
  })

  it('redraftBaseline POST /components/{t}/baseline/redraft（带 remark）', async () => {
    await redraftBaseline('sql', '轮一')
    expect(postSpy).toHaveBeenCalledWith('/components/sql/baseline/redraft', { remark: '轮一' })
  })

  it('redraftBaseline 不传 remark 时发空 body {}', async () => {
    await redraftBaseline('sql')
    expect(postSpy).toHaveBeenCalledWith('/components/sql/baseline/redraft', {})
  })

  it('discardBaselineRevision POST /components/{t}/baseline/discard_draft 空 body', async () => {
    await discardBaselineRevision('sql')
    expect(postSpy).toHaveBeenCalledWith('/components/sql/baseline/discard_draft', {})
  })
})

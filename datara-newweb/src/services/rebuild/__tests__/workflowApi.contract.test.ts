/**
 * INC4-FE-4 workflowApi 契约测试（/api/v1/rebuild/workflows 真实端点接线）。
 *
 * 覆盖（真源 datara-backend/rebuild/workflow/api.py + http.ts 单 BASE 底座）：
 *  1. list：GET /rebuild/workflows?project_id=（camel→snake 序列化）+ token 头；
 *     wire {definition_id,name,tags?,code?} → WorkflowDefSummary{id,name,tags??[],code}
 *     映射（data 纯数组直存，非分页对象——repository._definition_payload 语义）；
 *  2. list 容错：wire 缺 tags/code（后端补字段前，候裁披露②）→ tags=[]、code=undefined；
 *  3. delete：POST /{definition_id}/delete + JSON body {project_id}（data {deleted:true}）；
 *  4. 系统错误：非 2xx（后端 project_id 缺省 → 400/4001）默认丢包络码保 HTTP 状态码
 *     （preserveEnvelopeCode 未开，与底座默认行为一致）；
 *  5. categories 系四方法 RED 哨兵 WF_CATEGORIES_NOT_WIRED（端点缺位候裁披露①，接驳即活）。
 *
 * 范式：vi.stubGlobal('fetch') 直测 http 底座真实调用形状（沿 monitorApi.contract 先例）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  deleteWorkflowDefinition,
  listWorkflowDefinitions,
  WF_CATEGORIES_NOT_WIRED,
  workflowCategories,
} from '../workflowApi'

afterEach(() => vi.unstubAllGlobals())

/** 包络 2xx 响应（code=0 成功态） */
const ENV = (data: unknown, status = 200) =>
  new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status })

describe('INC4-FE-4 workflowApi 契约（/api/v1/rebuild/workflows）', () => {
  it('list：GET project_id 查询串（camel→snake）+ token 头 + wire→summary 映射（纯数组）', async () => {
    localStorage.setItem('datara_token', 'wf-token')
    const data = [
      { definition_id: 42, project_id: 7, name: '客户画像', description: null, current_version: 3, tags: ['同步'], code: 3 },
      { definition_id: 43, project_id: 7, name: '实时清洗', description: null, current_version: 1, tags: [] },
    ]
    const fetchMock = vi.fn().mockResolvedValue(ENV(data))
    vi.stubGlobal('fetch', fetchMock)
    const rows = await listWorkflowDefinitions(7)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toEqual({ id: 42, name: '客户画像', tags: ['同步'], code: 3 })
    // wire tags 空数组直通 + code 缺省 → undefined（三分类收窄：[] 落根目录）
    expect(rows[1]).toEqual({ id: 43, name: '实时清洗', tags: [], code: undefined })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/workflows?project_id=7')
    expect(init.method).toBe('GET')
    expect(new Headers(init.headers).get('token')).toBe('wf-token')
  })

  it('list 容错：wire 完全缺 tags/code 字段（后端补字段前）→ tags 空数组兜底', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(ENV([{ definition_id: 1, project_id: 7, name: '旧定义', description: null, current_version: null }])),
    )
    const rows = await listWorkflowDefinitions(7)
    expect(rows).toHaveLength(1)
    expect(rows[0].tags).toEqual([])
    expect(rows[0].code).toBeUndefined()
  })

  it('delete：POST /{definition_id}/delete + JSON body {project_id}（data {deleted:true} 不消费，resolve void）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ENV({ deleted: true }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(deleteWorkflowDefinition(7, 42)).resolves.toBeUndefined()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/workflows/42/delete')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ project_id: 7 }))
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })

  it('系统错误：后端 400/4001（project_id 缺省语义）→ 默认保 HTTP 状态码（包络码不透出）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ENV({ code: 4001, msg: 'project_id required' }, 400)))
    await expect(listWorkflowDefinitions(7)).rejects.toMatchObject({
      name: 'ContractApiError',
      httpStatus: 400,
      code: 400,
    })
  })

  it('categories 系四方法全 RED：rejects WF_CATEGORIES_NOT_WIRED（端点缺位，接驳即活）', async () => {
    await expect(workflowCategories.listCategories()).rejects.toThrow(WF_CATEGORIES_NOT_WIRED)
    await expect(workflowCategories.createCategory('自定义目录')).rejects.toThrow(WF_CATEGORIES_NOT_WIRED)
    await expect(workflowCategories.deleteCategory('自定义目录')).rejects.toThrow(WF_CATEGORIES_NOT_WIRED)
    await expect(workflowCategories.setWfTags(42, ['同步'])).rejects.toThrow(WF_CATEGORIES_NOT_WIRED)
  })
})

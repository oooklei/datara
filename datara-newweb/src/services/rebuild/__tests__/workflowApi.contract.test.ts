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
 * FE-6 扩容覆盖（六模型面：定义 CRUD + draft 节点/边 upsert/delete + 发布/版本读取）：
 *  6. WF_NODE_TYPES 13 值白名单冻结（门 2 数据模型对齐 repository.VALID_NODE_TYPES）；
 *  7. create：POST / body {project_id,name,description?}（条件键展开，缺省不携带）
 *     → WorkflowDefinitionInfo 映射；
 *  8. get：GET /{id}?project_id → payload + draft snake→camel 对拍（node_code→nodeCode /
 *     node_type→nodeType / position_x→positionX / from_node→fromNode）+ draft 缺省容错；
 *  9. update：POST /{id}/updates body 键对拍（name/description 单传与双传）；
 * 10. node upsert/delete：body 六键显式携带（null 直传）+ nodes/delete {project_id,node_code}；
 * 11. edge upsert/delete：body {project_id,from_node,to_node,name?} + edges/delete；
 * 12. publish：POST /{id}/publish {project_id,remark?} → WorkflowVersion（nodeCount/edgeCount）；
 * 13. versions/version：GET /{id}/versions[/v]?project_id → 列表映射 + 详情（nodes/edges/
 *     publish_record→publishRecord，缺省 null）；
 * 14. 域错误：WF_NAME_CONFLICT 409 默认保 HTTP 状态码（包络码不透出，沿用例 4 范式）。
 *
 * 范式：vi.stubGlobal('fetch') 直测 http 底座真实调用形状（沿 monitorApi.contract 先例）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createWorkflowDefinition,
  deleteWorkflowDefinition,
  deleteWorkflowDraftEdge,
  deleteWorkflowDraftNode,
  getWorkflowDefinition,
  getWorkflowVersion,
  listWorkflowDefinitions,
  listWorkflowVersions,
  publishWorkflowDefinition,
  updateWorkflowDefinition,
  upsertWorkflowDraftEdge,
  upsertWorkflowDraftNode,
  WF_CATEGORIES_NOT_WIRED,
  WF_NODE_TYPES,
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

describe('INC4-FE-6 workflowApi 六模型扩容契约', () => {
  it('WF_NODE_TYPES 白名单冻结：13 值恒定（门 2 对齐 repository.VALID_NODE_TYPES）', () => {
    expect([...WF_NODE_TYPES]).toEqual([
      'FLOW', 'SYNC', 'SQL', 'PYTHON', 'SHELL', 'DEPENDENCY', 'START', 'END',
      'CONDITION', 'FORK', 'JOIN', 'WAIT', 'SUB_WORKFLOW',
    ])
    expect(WF_NODE_TYPES).toHaveLength(13)
  })

  it('create：POST / body {project_id,name,description} → WorkflowDefinitionInfo 映射', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      ENV({ definition_id: 42, project_id: 7, name: '客户画像', description: '画像加工', current_version: null }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const info = await createWorkflowDefinition(7, '客户画像', '画像加工')
    expect(info).toEqual({ id: 42, projectId: 7, name: '客户画像', description: '画像加工', currentVersion: null })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/workflows')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ project_id: 7, name: '客户画像', description: '画像加工' }))
  })

  it('create 容错：description 缺省 → body 不携带该键（条件键展开）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      ENV({ definition_id: 42, project_id: 7, name: '新工作流', description: null, current_version: null }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await createWorkflowDefinition(7, '新工作流')
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.body).toBe(JSON.stringify({ project_id: 7, name: '新工作流' }))
  })

  it('get：GET /{id}?project_id → payload + draft snake→camel 对拍（node/edge 全字段）', async () => {
    const data = {
      definition_id: 42, project_id: 7, name: '客户画像', description: null, current_version: null,
      draft: {
        nodes: [
          { node_code: 'n1', node_type: 'SQL', name: null, params: { sql: 'select 1' }, position_x: 100, position_y: 200 },
          { node_code: 'n2', node_type: 'SYNC', name: '同步', params: null, position_x: null, position_y: null },
        ],
        edges: [{ from_node: 'n1', to_node: 'n2', name: null }],
      },
    }
    const fetchMock = vi.fn().mockResolvedValue(ENV(data))
    vi.stubGlobal('fetch', fetchMock)
    const info = await getWorkflowDefinition(7, 42)
    expect(info).toEqual({
      id: 42, projectId: 7, name: '客户画像', description: null, currentVersion: null,
      draft: {
        nodes: [
          { nodeCode: 'n1', nodeType: 'SQL', name: null, params: { sql: 'select 1' }, positionX: 100, positionY: 200 },
          { nodeCode: 'n2', nodeType: 'SYNC', name: '同步', params: null, positionX: null, positionY: null },
        ],
        edges: [{ fromNode: 'n1', toNode: 'n2', name: null }],
      },
    })
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/workflows/42?project_id=7')
  })

  it('get 容错：draft 缺省 → 空 draft（nodes/edges 空数组兜底）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      ENV({ definition_id: 42, project_id: 7, name: '空定义', description: null, current_version: null }),
    ))
    const info = await getWorkflowDefinition(7, 42)
    expect(info.draft).toEqual({ nodes: [], edges: [] })
  })

  it('update：POST /{id}/updates body 键对拍（name 单传 / description 单传 / 双传）', async () => {
    // 多次调用须每次新建 Response（happy-dom body 一次性，不可复用实例）
    const fetchMock = vi.fn().mockImplementation(() =>
      ENV({ definition_id: 42, project_id: 7, name: '改名', description: null, current_version: null }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await updateWorkflowDefinition(7, 42, { name: '改名' })
    const [url, init1] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/workflows/42/updates')
    expect(init1.body).toBe(JSON.stringify({ project_id: 7, name: '改名' }))

    await updateWorkflowDefinition(7, 42, { description: '描述' })
    const [, init2] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(init2.body).toBe(JSON.stringify({ project_id: 7, description: '描述' }))

    await updateWorkflowDefinition(7, 42, { name: 'n', description: 'd' })
    const [, init3] = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(init3.body).toBe(JSON.stringify({ project_id: 7, name: 'n', description: 'd' }))
  })

  it('node upsert：POST /{id}/nodes body 六键显式携带（null 直传）+ wire→camel 回程', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      ENV({ node_code: 'n1', node_type: 'SQL', name: null, params: { sql: 'select 1' }, position_x: 10, position_y: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const node = await upsertWorkflowDraftNode(7, 42, {
      nodeCode: 'n1', nodeType: 'SQL', name: null, params: { sql: 'select 1' }, positionX: 10, positionY: 20,
    })
    expect(node).toEqual({ nodeCode: 'n1', nodeType: 'SQL', name: null, params: { sql: 'select 1' }, positionX: 10, positionY: 20 })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/workflows/42/nodes')
    expect(init.body).toBe(JSON.stringify({
      project_id: 7, node_code: 'n1', node_type: 'SQL', name: null, params: { sql: 'select 1' }, position_x: 10, position_y: 20,
    }))
  })

  it('node delete：POST /{id}/nodes/delete body {project_id,node_code}（级联删触边，resolve void）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ENV({ deleted: true }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(deleteWorkflowDraftNode(7, 42, 'n1')).resolves.toBeUndefined()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/workflows/42/nodes/delete')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ project_id: 7, node_code: 'n1' }))
  })

  it('edge upsert/delete：POST /{id}/edges（(from,to) upsert）与 /{id}/edges/delete body 对拍', async () => {
    // 多次调用须每次新建 Response（happy-dom body 一次性，不可复用实例）
    const fetchMock = vi.fn().mockImplementation(() => ENV({ from_node: 'n1', to_node: 'n2', name: '连线' }))
    vi.stubGlobal('fetch', fetchMock)
    const edge = await upsertWorkflowDraftEdge(7, 42, { fromNode: 'n1', toNode: 'n2', name: '连线' })
    expect(edge).toEqual({ fromNode: 'n1', toNode: 'n2', name: '连线' })
    const [url1, init1] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url1).toBe('/api/v1/rebuild/workflows/42/edges')
    expect(init1.body).toBe(JSON.stringify({ project_id: 7, from_node: 'n1', to_node: 'n2', name: '连线' }))

    await expect(deleteWorkflowDraftEdge(7, 42, 'n1', 'n2')).resolves.toBeUndefined()
    const [url2, init2] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(url2).toBe('/api/v1/rebuild/workflows/42/edges/delete')
    expect(init2.body).toBe(JSON.stringify({ project_id: 7, from_node: 'n1', to_node: 'n2' }))
  })

  it('publish：POST /{id}/publish body {project_id,remark} → WorkflowVersion 映射（nodeCount/edgeCount）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      ENV({
        definition_id: 42, version: 3, status: 'published', remark: '首发',
        snapshot_digest: 'sha256:abc', published_at: '2026-10-21T00:00:00Z', published_by: 'op',
        node_count: 2, edge_count: 1,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const version = await publishWorkflowDefinition(7, 42, '首发')
    expect(version).toEqual({
      definitionId: 42, version: 3, status: 'published', remark: '首发',
      snapshotDigest: 'sha256:abc', publishedAt: '2026-10-21T00:00:00Z', publishedBy: 'op',
      nodeCount: 2, edgeCount: 1,
    })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/workflows/42/publish')
    expect(init.body).toBe(JSON.stringify({ project_id: 7, remark: '首发' }))
  })

  it('publish 容错：remark 缺省 → body 不携带该键；wire 缺 node_count/edge_count → undefined', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      ENV({
        definition_id: 42, version: 1, status: 'published', remark: null,
        snapshot_digest: 'sha256:abc', published_at: null, published_by: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const version = await publishWorkflowDefinition(7, 42)
    expect(version.remark).toBeNull()
    expect(version.nodeCount).toBeUndefined()
    expect(version.edgeCount).toBeUndefined()
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.body).toBe(JSON.stringify({ project_id: 7 }))
  })

  it('versions：GET /{id}/versions?project_id → version payload[] 映射', async () => {
    const data = [
      { definition_id: 42, version: 1, status: 'published', remark: null, snapshot_digest: 'd1', published_at: '2026-10-20T00:00:00Z', published_by: 'op' },
      { definition_id: 42, version: 2, status: 'published', remark: 'v2', snapshot_digest: 'd2', published_at: null, published_by: null },
    ]
    const fetchMock = vi.fn().mockResolvedValue(ENV(data))
    vi.stubGlobal('fetch', fetchMock)
    const rows = await listWorkflowVersions(7, 42)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toEqual({ definitionId: 42, version: 1, status: 'published', remark: null, snapshotDigest: 'd1', publishedAt: '2026-10-20T00:00:00Z', publishedBy: 'op' })
    expect(rows[1].publishedAt).toBeNull()
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/workflows/42/versions?project_id=7')
  })

  it('version 详情：GET /{id}/versions/{v}?project_id → nodes/edges/publishRecord 映射', async () => {
    const data = {
      definition_id: 42, version: 1, status: 'published', remark: 'v1', snapshot_digest: 'd1',
      published_at: '2026-10-20T00:00:00Z', published_by: 'op', node_count: 1, edge_count: 0,
      nodes: [{ node_code: 'n1', node_type: 'FLOW', name: null, params: null, position_x: 0, position_y: 0 }],
      edges: [],
      publish_record: { version_id: 9, version: 1, remark: 'v1', published_by: 'op', published_at: '2026-10-20T00:00:00Z' },
    }
    const fetchMock = vi.fn().mockResolvedValue(ENV(data))
    vi.stubGlobal('fetch', fetchMock)
    const detail = await getWorkflowVersion(7, 42, 1)
    expect(detail.nodes).toEqual([{ nodeCode: 'n1', nodeType: 'FLOW', name: null, params: null, positionX: 0, positionY: 0 }])
    expect(detail.edges).toEqual([])
    expect(detail.publishRecord).toEqual({ versionId: 9, version: 1, remark: 'v1', publishedBy: 'op', publishedAt: '2026-10-20T00:00:00Z' })
    expect(detail.nodeCount).toBe(1)
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/workflows/42/versions/1?project_id=7')
  })

  it('version 详情容错：publish_record/nodes/edges 缺省 → null/空数组兜底', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      ENV({
        definition_id: 42, version: 1, status: 'published', remark: null,
        snapshot_digest: 'd1', published_at: null, published_by: null,
      }),
    ))
    const detail = await getWorkflowVersion(7, 42, 1)
    expect(detail.publishRecord).toBeNull()
    expect(detail.nodes).toEqual([])
    expect(detail.edges).toEqual([])
  })

  it('域错误：WF_NAME_CONFLICT 409 → 默认保 HTTP 状态码（包络码不透出）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ENV({ code: 4201, msg: 'workflow name conflict' }, 409)))
    await expect(createWorkflowDefinition(7, '重名')).rejects.toMatchObject({
      name: 'ContractApiError',
      httpStatus: 409,
      code: 409,
    })
  })
})

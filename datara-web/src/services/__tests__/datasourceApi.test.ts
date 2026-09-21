/**
 * datasourceApi 契约测试（I4 设计 §9 vitest 新增之三）：
 * 以 datara-backend/api/datasource.py 为唯一权威，验证 URL/方法/查询串/请求体
 * 与 {code,msg,data} 解包、错误抛出语义（graphApi 先例同款 stub fetch 方案）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createDataSource, deleteDataSource, deleteTmpData, getDataSourceTree,
  listDataFiles, listDataSources, listTmpData, testDataSource, updateDataSource,
} from '../datasourceApi'
import { TOKEN_KEY } from '../http'

const fetchMock = vi.fn()
function stubRes(data: unknown, code = 0, msg = '') {
  fetchMock.mockResolvedValueOnce({ json: async () => ({ code, msg, data }) })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('localStorage', { getItem: () => 'tok-i4', setItem: vi.fn(), removeItem: vi.fn() })
})

describe('数据源 CRUD 契约', () => {
  it('listDataSources → GET /datasources（带 token header，解包 data）', async () => {
    stubRes([{ id: 1, name: '内置源库-ec_retail', type: 'mysql' }])
    const rows = await listDataSources()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/datasources')
    expect(init.method).toBe('GET')
    expect(init.headers.token).toBe('tok-i4')
    expect(rows[0].name).toBe('内置源库-ec_retail')
  })

  it('listDataSources 筛选参数 → 查询串按需拼接', async () => {
    stubRes([])
    await listDataSources({ keyword: 'retail', type: 'file', env: '测试', group: '交易域' })
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/datasources?keyword=retail&env=' + encodeURIComponent('测试') + '&group=' + encodeURIComponent('交易域') + '&type=file')
  })

  it('createDataSource → POST 全量 body；updateDataSource → PUT /{id}', async () => {
    stubRes({ id: 3, name: '样例文件源', type: 'file' })
    const body = { name: '样例文件源', type: 'file', params: { format: 'csv', path: 'a.csv' } }
    const row = await createDataSource(body)
    expect(row.id).toBe(3)
    let [url, init] = fetchMock.mock.calls[0]
    expect([url, init.method, init.body]).toEqual(['/api/v1/datasources', 'POST', JSON.stringify(body)])

    stubRes(null)
    await updateDataSource(3, body)
    ;[url, init] = fetchMock.mock.calls[1]
    expect([url, init.method]).toEqual(['/api/v1/datasources/3', 'PUT'])
  })

  it('deleteDataSource → DELETE /{id}；testDataSource → POST /{id}/test', async () => {
    stubRes(null)
    await deleteDataSource('内置源库-ec_retail')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/datasources/' + encodeURIComponent('内置源库-ec_retail'))

    stubRes({ status: 'online', elapsedMs: 12, message: '连通成功（SELECT 1）' })
    const r = await testDataSource(2)
    expect(fetchMock.mock.calls[1]).toEqual(['/api/v1/datasources/2/test', expect.objectContaining({ method: 'POST' })])
    expect(r.status).toBe('online')
  })
})

describe('库表树 / 文件清单契约', () => {
  it('getDataSourceTree 连接型 + db 过滤 → /tree?db=', async () => {
    stubRes({ kind: 'connection', databases: [] })
    await getDataSourceTree(1, 'ec_retail')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/datasources/1/tree?db=ec_retail')
  })

  it('getDataSourceTree 文件型（无 db 过滤）', async () => {
    stubRes({ kind: 'file', file: 'a.csv', schema: { columns: [], sampledRows: 0 }, sample: [] })
    const t = await getDataSourceTree(5)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/datasources/5/tree')
    expect(t.kind).toBe('file')
  })

  it('listDataFiles → GET /datasources/files', async () => {
    stubRes(['samples/orders.csv'])
    const files = await listDataFiles()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/datasources/files')
    expect(files).toEqual(['samples/orders.csv'])
  })
})

describe('临时数据契约（C22 预览网格数据源）', () => {
  it('listTmpData → GET /tmp-data?instance_id=', async () => {
    stubRes([{ id: 9, instanceId: 'I-1', preview: { columns: ['id'], rows: [['1']] } }])
    const rows = await listTmpData('I-1')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/tmp-data?instance_id=I-1')
    expect(rows[0].preview?.columns).toEqual(['id'])
  })

  it('deleteTmpData → DELETE /tmp-data/{id}', async () => {
    stubRes(null)
    await deleteTmpData(9)
    expect(fetchMock.mock.calls[0]).toEqual(['/api/v1/tmp-data/9', expect.objectContaining({ method: 'DELETE' })])
  })
})

describe('错误语义（graphApi 先例同款）', () => {
  it('code!==0 → throw Error(msg)', async () => {
    stubRes(null, 4001, '数据源不存在')
    await expect(testDataSource(99)).rejects.toThrow('数据源不存在')
  })

  it('非 JSON 响应 → 解析失败提示', async () => {
    fetchMock.mockResolvedValueOnce({ json: async () => null, status: 502 })
    await expect(listDataSources()).rejects.toThrow('响应解析失败')
  })

  it('token key 常量稳定（localStorage 契约）', () => {
    expect(TOKEN_KEY).toBe('datara_token')
  })
})

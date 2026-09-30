/**
 * lineageApi 契约测试（I5 设计 §9 vitest 新增）：
 * 以 datara-backend/api/lineage.py 为唯一权威，验证四端点 URL/查询串/方法
 * 与 {code,msg,data} 解包语义（datasourceApi 先例同款 stub fetch 方案）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fetchLineageGraph, lineageStats, lineageTrace, listFieldLineage, listTableLineage,
} from '../lineageApi'

const fetchMock = vi.fn()
function stubRes(data: unknown, code = 0, msg = '') {
  fetchMock.mockResolvedValueOnce({ json: async () => ({ code, msg, data }) })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('localStorage', { getItem: () => 'tok-i5', setItem: vi.fn(), removeItem: vi.fn() })
})

describe('/lineage/tables 契约', () => {
  it('无参 → GET /lineage/tables（解包 data）', async () => {
    stubRes([{
      from: 'ods_order', to: 'dwd_order_pay_detail', task: 'etl_pay_clean', wf: '支付清洗',
      instanceId: 'i-1', nodeId: 'n1', dsName: 'src', tmpFlag: 0, stmt: 'INSERT INTO dwd_order_pay_detail ...',
      stmtNo: 0, wfCode: 101, createTime: '2026-09-18 10:00:00',
    }])
    const rows = await listTableLineage()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/lineage/tables')
    expect(init.method).toBe('GET')
    expect(init.headers.token).toBe('tok-i5')
    expect(rows[0].from).toBe('ods_order')
    expect(rows[0].tmpFlag).toBe(0)
  })

  it('过滤参数 → 查询串按需拼接（instance_id/table/keyword/wf_code）', async () => {
    stubRes([])
    await listTableLineage({ instance_id: 'i-9', table: 'dwd_order_pay_detail' })
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/lineage/tables?instance_id=i-9&table=dwd_order_pay_detail',
    )

    stubRes([])
    await listTableLineage({ keyword: 'pay', wf_code: 101 })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/lineage/tables?keyword=pay&wf_code=101')
  })
})

describe('/lineage/fields 契约', () => {
  it('无参 → GET /lineage/fields，映射键为目标字段全名', async () => {
    stubRes({
      'dwd_order_pay_detail.net_amount': [
        { from: 'ods_order.amount', transform: 'amount * 0.9' },
      ],
    })
    const fields = await listFieldLineage()
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/lineage/fields')
    expect(fields['dwd_order_pay_detail.net_amount']![0].transform).toBe('amount * 0.9')
  })

  it('table/wf_code 过滤 → 查询串拼接', async () => {
    stubRes({})
    await listFieldLineage({ table: 'ods_order', wf_code: 7 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/lineage/fields?table=ods_order&wf_code=7')
  })
})

describe('/lineage/stats 与 /lineage/trace 契约', () => {
  it('stats → GET /lineage/stats（统计字段直出）', async () => {
    stubRes({ edgeCount: 12, fieldCount: 40, tableCount: 9, wfCount: 3, lastTime: '2026-09-18 11:00:00' })
    const s = await lineageStats()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/lineage/stats')
    expect(s.edgeCount).toBe(12)
    expect(s.wfCount).toBe(3)
  })

  it('trace → GET /lineage/trace?instance_id=…（node_id 按需）', async () => {
    stubRes([{ from: 'ods_order', to: 'dwd_order_pay_detail', fields: [] }])
    const rows = await lineageTrace('i-5')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/lineage/trace?instance_id=i-5')
    expect(rows[0].to).toBe('dwd_order_pay_detail')

    stubRes([])
    await lineageTrace('i-5', 'n_sql_1')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/lineage/trace?instance_id=i-5&node_id=n_sql_1')
  })

  it('code!==0 → 抛 Error(msg)（http 统一语义）', async () => {
    stubRes(null, 5100, '实例不存在')
    await expect(lineageTrace('nope')).rejects.toThrow('实例不存在')
  })
})

describe('/lineage/graph 契约（Task 5 血缘图聚合）', () => {
  it('最小参 → GET /lineage/graph?level=table（level 必传）', async () => {
    stubRes({ nodes: [], edges: [], opaques: [], truncated: false })
    const res = await fetchLineageGraph({ level: 'table' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/lineage/graph?level=table')
    expect(init.method).toBe('GET')
    expect(init.headers.token).toBe('tok-i5')
    expect(res.truncated).toBe(false)
  })

  it('全参 → 查询串按序拼接（source/wfCode/table/direction/depth/limit）', async () => {
    stubRes({ nodes: [], edges: [], opaques: [], truncated: false })
    await fetchLineageGraph({
      level: 'table', source: 'design', wfCode: 101, table: 'dwd_order_pay_detail',
      direction: 'downstream', depth: 0, limit: 50,
    })
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/lineage/graph?level=table&source=design&wfCode=101'
      + '&table=dwd_order_pay_detail&direction=downstream&depth=0&limit=50',
    )
  })

  it('返回 data 直出（nodes/edges/opaques/truncated 形状）', async () => {
    stubRes({
      nodes: [{
        fq: 'dwd_order_pay_detail', ds: 'dw', table: 'dwd_order_pay_detail', tmpFlag: 0,
        sources: ['design', 'runtime'], wfs: [101],
      }],
      edges: [{
        from: 'ods_order', to: 'dwd_order_pay_detail', level: 'table',
        sources: ['runtime'],
        refs: [{ wfCode: 101, nodeId: 'n_sql_1', stmtNo: 0 }],
      }],
      opaques: [{ wfCode: 101, nodeId: 'n_x', type: 'notify', reason: '不产边' }],
      truncated: true,
    })
    const res = await fetchLineageGraph({ level: 'field', source: 'all' })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/lineage/graph?level=field&source=all')
    expect(res.nodes[0]!.sources).toEqual(['design', 'runtime'])
    expect(res.edges[0]!.refs[0]!.nodeId).toBe('n_sql_1')
    expect(res.opaques[0]!.type).toBe('notify')
    expect(res.truncated).toBe(true)
  })
})

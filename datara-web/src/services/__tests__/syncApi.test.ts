/**
 * syncApi 契约测试（I6 设计 §6/§9，F34）：
 * 以 datara-backend/api/sync.py 为唯一权威，验证两接口 URL/方法/查询串/解包、
 * 错误抛出语义（datasourceApi 先例同款 stub fetch 方案）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listSyncInstances, listSyncTasks } from '../syncApi'

const fetchMock = vi.fn()
function stubRes(data: unknown, code = 0, msg = '') {
  fetchMock.mockResolvedValueOnce({ json: async () => ({ code, msg, data }) })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('localStorage', { getItem: () => 'tok-i6', setItem: vi.fn(), removeItem: vi.fn() })
})

describe('syncApi 契约（api/sync.py）', () => {
  it('listSyncTasks → GET /sync-tasks（keyword/state 查询串按需拼接，解包 data）', async () => {
    stubRes({
      total: 1,
      list: [{
        wfCode: 5, name: '零售多分区同步', tags: ['同步'], instanceCount: 3,
        lastInstanceId: 'inst_abc', lastState: 'success', lastTime: '2026-09-19 10:00',
        readRows: 120, writeRows: 118, badRows: 2, schemas: ['ec_retail_east', 'ec_retail_south'],
      }],
    })
    const page = await listSyncTasks({ pageNo: 2, pageSize: 30, keyword: '零售', state: 'success' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/sync-tasks?page_no=2&page_size=30&keyword=' + encodeURIComponent('零售') + '&state=success')
    expect(init.method).toBe('GET')
    expect(init.headers.token).toBe('tok-i6')
    expect(page.total).toBe(1)
    expect(page.list[0].wfCode).toBe(5)
    expect(page.list[0].schemas).toEqual(['ec_retail_east', 'ec_retail_south'])
  })

  it('listSyncTasks 缺省参数 → 仅 page_no/page_size；空筛选项不拼接', async () => {
    stubRes({ total: 0, list: [] })
    await listSyncTasks()
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/sync-tasks?page_no=1&page_size=50')
  })

  it('listSyncInstances → GET /sync-tasks/{wfCode}/instances（state 按需拼接）', async () => {
    stubRes({
      total: 1,
      list: [{
        instanceId: 'inst_abc', state: 'success', runMode: 'manual',
        startTime: '2026-09-19 10:00', endTime: '2026-09-19 10:01', batchId: 'inst_abc',
        readRows: 120, writeRows: 118, badRows: 2, schemas: ['ec_retail_east'],
      }],
    })
    const page = await listSyncInstances(7, { pageNo: 1, pageSize: 20, state: 'failure' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/sync-tasks/7/instances?page_no=1&page_size=20&state=failure')
    expect(init.method).toBe('GET')
    expect(page.list[0].batchId).toBe('inst_abc') // 批次号=instance_id（裁定③）
  })

  it('code!==0 → throw Error(msg)（未打同步标签语义）', async () => {
    stubRes(null, 4004, '工作流未打同步标签: x')
    await expect(listSyncInstances(9)).rejects.toThrow('工作流未打同步标签')
  })
})

import {afterEach,describe,expect,it,vi} from 'vitest'
import {
  QUALITY_ERROR_CODES,
  QUALITY_PERMISSION_MATRIX,
  QUALITY_STRUCTURAL_ONLY,
  governanceApi,
} from '../governanceApi'

/** 包络三态构造：`code===0` → 200，否则按后端 `fail()` 口径给非 2xx + 包络码。 */
const envelope = (data: unknown, code = 0, msg = 'success') =>
  new Response(JSON.stringify({ code, msg, data }), {
    status: code === 0 ? 200 : 403,
    headers: { 'Content-Type': 'application/json' },
  })

afterEach(() => vi.unstubAllGlobals())

describe('14.4 质量域契约层（IMPL-v4-07）', () => {
  it('freezes separated permission surface and structural semantics', () => {
    expect(QUALITY_PERMISSION_MATRIX).toEqual({
      listRules: 'VIEW_ALL',
      createRule: 'EDIT_DEFINITION',
      updateRule: 'EDIT_DEFINITION',
      runRule: 'EDIT_DEFINITION',
      listRuns: 'VIEW_ALL',
    })
    expect(QUALITY_ERROR_CODES).toMatchObject({
      permissionDenied: 1003,
      notFound: 4041,
      duplicateName: 4091,
      disabled: 4091,
    })
    expect(QUALITY_STRUCTURAL_ONLY.engine).toBe('structural')
  })

  it('maps all four frozen endpoints with methods and pagination', async () => {
    const calls: Array<[string, RequestInit | undefined]> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (u: string | URL | Request, i?: RequestInit) => {
        calls.push([String(u), i])
        const method = i?.method ?? 'GET'
        if (method === 'POST' && /\/quality-rules\/\d+\/run$/.test(String(u))) {
          return envelope({ asset_id: 9, id: 3, rule_id: 5 })
        }
        if (method === 'POST') return envelope({ id: 5, project_id: 1 })
        return envelope({ total: 0, list: [] })
      }),
    )

    await governanceApi.listRules(1)
    await governanceApi.createRule(1, {
      assetId: 9,
      name: '主键非空',
      expression: 'id IS NOT NULL',
      severity: 'error',
      enabled: true,
    })
    await governanceApi.runRule(1, 5)
    await governanceApi.listRuns(1, 2, 20)

    expect(calls.map(([u, i]) => [u, i?.method ?? 'GET'])).toEqual([
      ['/api/v1/rebuild/governance/projects/1/quality-rules?page=1&page_size=50', 'GET'],
      ['/api/v1/rebuild/governance/projects/1/quality-rules', 'POST'],
      ['/api/v1/rebuild/governance/projects/1/quality-rules/5/run', 'POST'],
      ['/api/v1/rebuild/governance/projects/1/quality-runs?page=2&page_size=20', 'GET'],
    ])
  })

  it('converts FE camelCase to wire snake_case and BE snake_case to FE camelCase', async () => {
    let sentBody = ''
    vi.stubGlobal(
      'fetch',
      vi.fn(async (u: string | URL | Request, i?: RequestInit) => {
        if ((i?.method ?? 'GET') === 'POST' && !/\/run$/.test(String(u))) {
          sentBody = String(i?.body ?? '')
          return envelope({
            id: 5,
            project_id: 1,
            asset_id: 9,
            name: '主键非空',
            expression: 'id IS NOT NULL',
            severity: 'error',
            enabled: true,
            created_at: '2026-10-22T10:00:00Z',
            updated_at: null,
          })
        }
        return envelope({
          total: 1,
          list: [
            {
              asset_id: 9,
              id: 3,
              rule_id: 5,
              status: 'succeeded',
              checked_rows: 0,
              success_rows: 0,
              failed_rows: 0,
              skipped_rows: 0,
              summary: { engine: 'structural', message: 'structural predicate validation only', issues: [] },
              generated_at: '2026-10-22T10:05:00Z',
            },
          ],
        })
      }),
    )

    const created = await governanceApi.createRule(1, {
      assetId: 9,
      name: '主键非空',
      expression: 'id IS NOT NULL',
      severity: 'error',
      enabled: true,
    })
    expect(sentBody).toBe(
      JSON.stringify({
        asset_id: 9,
        name: '主键非空',
        expression: 'id IS NOT NULL',
        severity: 'error',
        enabled: true,
      }),
    )
    expect(created).toMatchObject({
      id: 5,
      projectId: 1,
      assetId: 9,
      severity: 'error',
      enabled: true,
      createdAt: '2026-10-22T10:00:00Z',
      updatedAt: null,
    })

    const page = await governanceApi.listRuns(1)
    expect(page.total).toBe(1)
    expect(page.list[0]).toMatchObject({
      id: 3,
      assetId: 9,
      ruleId: 5,
      status: 'succeeded',
      // structural 红线：行级四字段恒 0，前端不得虚构行级结果
      checkedRows: 0,
      successRows: 0,
      failedRows: 0,
      skippedRows: 0,
      generatedAt: '2026-10-22T10:05:00Z',
    })
    expect(page.list[0]?.summary.engine).toBe('structural')
    expect(page.list[0]?.summary.issues).toEqual([])
  })

  it('preserves backend business error codes instead of collapsing to HTTP status', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => envelope(null, 4091, 'quality rule name already exists')))
    await expect(
      governanceApi.createRule(1, {
        assetId: 9,
        name: '主键非空',
        expression: 'id IS NOT NULL',
        severity: 'error',
        enabled: true,
      }),
    ).rejects.toMatchObject({ code: 4091 })
  })

  it('surfaces permission denial as 1003 for write surface without list outage', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => envelope(null, 1003, 'permission denied')))
    await expect(governanceApi.runRule(1, 5)).rejects.toMatchObject({ code: 1003 })
  })
})

/** inc14 治理域其余 13 方法（资产 / 标签 / 血缘 / 标准 / 指标 / 审计）冻结面。 */
describe('14.4 治理域资产/标签/血缘/标准/指标/审计契约面', () => {
  const stub = (handler?: (u: string, i?: RequestInit) => Response | Promise<Response>) =>
    vi.fn(async (u: string | URL | Request, i?: RequestInit) => {
      calls.push([String(u), i])
      return handler ? handler(String(u), i) : envelope({ total: 0, list: [] })
    })

  let calls: Array<[string, RequestInit | undefined]> = []

  it('maps asset endpoints with pagination filters and camel/snake conversion', async () => {
    calls = []
    vi.stubGlobal('fetch', stub(() => envelope({ total: 1, page: 1, page_size: 50, list: [{ id: 9, asset_name: 't_order' }] })))

    const page = await governanceApi.listAssets(1, { q: 'order', assetType: 'table', domain: 'trade', tag: 'core', page: 2, pageSize: 10 })
    expect(calls[0]?.[0]).toBe(
      '/api/v1/rebuild/governance/projects/1/assets?q=order&asset_type=table&domain=trade&tag=core&page=2&page_size=10',
    )
    expect(page.list[0]).toMatchObject({ id: 9, assetName: 't_order' })

    await governanceApi.getAsset(9)
    expect(calls[1]?.[0]).toBe('/api/v1/rebuild/governance/assets/9')
  })

  it('converts createAsset body to snake_case on the wire', async () => {
    calls = []
    let sentBody = ''
    vi.stubGlobal(
      'fetch',
      stub((u, i) => {
        if ((i?.method ?? 'GET') === 'POST') {
          sentBody = String(i?.body ?? '')
          return envelope({ id: 9, project_id: 1, asset_name: 't_order' })
        }
        return envelope({ total: 0, list: [] })
      }),
    )

    await governanceApi.createAsset(1, {
      sourceSystem: 'mysql',
      databaseName: 'dw',
      schemaName: 'ods',
      assetName: 't_order',
      assetType: 'table',
      displayName: '订单表',
      ownerName: 'alice',
      domainName: 'trade',
      rowCount: 1000,
      fields: [{ fieldName: 'id', ordinalPosition: 1, dataType: 'bigint', nullable: false, description: '主键' }],
    })

    expect(JSON.parse(sentBody)).toEqual({
      source_system: 'mysql',
      database_name: 'dw',
      schema_name: 'ods',
      asset_name: 't_order',
      asset_type: 'table',
      display_name: '订单表',
      owner_name: 'alice',
      domain_name: 'trade',
      row_count: 1000,
      fields: [{ field_name: 'id', ordinal_position: 1, data_type: 'bigint', nullable: false, description: '主键' }],
    })
  })

  it('maps tag definition and asset-tag assignment endpoints', async () => {
    calls = []
    let tagBody = ''
    let assignBody = ''
    vi.stubGlobal(
      'fetch',
      stub((u, i) => {
        if (String(u).endsWith('/tags') && (i?.method ?? 'GET') === 'POST') {
          tagBody = String(i?.body ?? '')
          return envelope({ id: 7, namespace: 'biz', tag_key: 'core', display_name: '核心' })
        }
        if (/\/assets\/9\/tags$/.test(String(u))) {
          assignBody = String(i?.body ?? '')
          return envelope({ asset_id: 9, tag_ids: [7] })
        }
        return envelope({ total: 0, list: [] })
      }),
    )

    await governanceApi.createTag(1, { namespace: 'biz', tagKey: 'core', displayName: '核心', description: '核心资产' })
    expect(JSON.parse(tagBody)).toEqual({
      namespace: 'biz',
      tag_key: 'core',
      display_name: '核心',
      description: '核心资产',
    })

    const assigned = await governanceApi.assignAssetTags(9, [7])
    // 冻结口径：assignAssetTags 不做 camelToSnake（wire 保持 tagIds）
    expect(assignBody).toBe(JSON.stringify({ tagIds: [7] }))
    expect(assigned).toEqual({ assetId: 9, tagIds: [7] })
  })

  it('maps lineage create/read with direction and depth defaults', async () => {
    calls = []
    let lineageBody = ''
    vi.stubGlobal(
      'fetch',
      stub((u, i) => {
        if ((i?.method ?? 'GET') === 'POST') {
          lineageBody = String(i?.body ?? '')
          return envelope({ id: 1, external_id: 'e1' })
        }
        return envelope({
          asset_id: 9,
          direction: 'both',
          depth: 3,
          nodes: [{ id: 9, asset_name: 't_order' }],
          edges: [{ id: 1, external_id: 'e1', source_asset_id: 8, target_asset_id: 9, lineage_type: 'derived' }],
        })
      }),
    )

    await governanceApi.createLineage(1, {
      externalId: 'e1',
      sourceAssetId: 8,
      targetAssetId: 9,
      sourceFieldName: 'order_id',
      targetFieldName: 'id',
      lineageType: 'derived',
      processRef: 'etl_orders',
    })
    expect(calls[0]?.[0]).toBe('/api/v1/rebuild/governance/projects/1/lineage')
    expect(JSON.parse(lineageBody)).toEqual({
      external_id: 'e1',
      source_asset_id: 8,
      target_asset_id: 9,
      source_field_name: 'order_id',
      target_field_name: 'id',
      lineage_type: 'derived',
      process_ref: 'etl_orders',
    })

    const graph = await governanceApi.getLineage(9)
    expect(calls[1]?.[0]).toBe('/api/v1/rebuild/governance/assets/9/lineage?direction=both&depth=3')
    expect(graph.nodes[0]).toMatchObject({ id: 9, assetName: 't_order' })
    expect(graph.edges[0]).toMatchObject({ externalId: 'e1', sourceAssetId: 8, targetAssetId: 9, lineageType: 'derived' })
  })

  it('maps standard list/create/check with check returning an array', async () => {
    calls = []
    let stdBody = ''
    vi.stubGlobal(
      'fetch',
      stub((u, i) => {
        if (/\/standards\/check$/.test(String(u))) {
          return envelope([{ standard_id: 9, code: 'STD001', passed: true, engine: 'structural', findings: [], checked_at: null }])
        }
        if ((i?.method ?? 'GET') === 'POST') {
          stdBody = String(i?.body ?? '')
          return envelope({ id: 9, project_id: 1, code: 'STD001', status: 'draft' })
        }
        return envelope({ total: 1, list: [{ id: 9, project_id: 1, code: 'STD001', status: 'draft' }] })
      }),
    )

    const page = await governanceApi.listStandards(1, 1, 50)
    expect(calls[0]?.[0]).toBe('/api/v1/rebuild/governance/projects/1/standards?page=1&page_size=50')
    expect(page.list[0]).toMatchObject({ id: 9, projectId: 1, code: 'STD001', status: 'draft' })

    await governanceApi.createStandard(1, { code: 'STD001', name: '金额非空', dataType: 'decimal', expression: 'not_null', description: '金额字段非空', status: 'draft' })
    expect(JSON.parse(stdBody)).toEqual({
      code: 'STD001',
      name: '金额非空',
      data_type: 'decimal',
      expression: 'not_null',
      description: '金额字段非空',
      status: 'draft',
    })

    const checks = await governanceApi.checkStandard(1, { standardId: 9 })
    expect(Array.isArray(checks)).toBe(true)
    expect(checks[0]).toMatchObject({ standardId: 9, code: 'STD001', passed: true, engine: 'structural' })
  })

  it('maps metric list/create and audit list endpoints', async () => {
    calls = []
    let metricBody = ''
    vi.stubGlobal(
      'fetch',
      stub((u, i) => {
        if ((i?.method ?? 'GET') === 'POST') {
          metricBody = String(i?.body ?? '')
          return envelope({ id: 4, project_id: 1, code: 'GMV', status: 'draft' })
        }
        if (/\/audit\?/.test(String(u))) {
          return envelope({ total: 1, list: [{ id: 1, actor_id: 2, action: 'create', resource_type: 'standard', resource_id: '9' }] })
        }
        return envelope({ total: 1, list: [{ id: 4, project_id: 1, code: 'GMV', status: 'draft' }] })
      }),
    )

    const page = await governanceApi.listMetrics(1)
    expect(calls[0]?.[0]).toBe('/api/v1/rebuild/governance/projects/1/metrics?page=1&page_size=50')
    expect(page.list[0]).toMatchObject({ id: 4, projectId: 1, code: 'GMV', status: 'draft' })

    await governanceApi.createMetric(1, { code: 'GMV', name: '成交总额', formula: 'sum(amount)', description: '成交额口径', status: 'draft' })
    expect(JSON.parse(metricBody)).toEqual({
      code: 'GMV',
      name: '成交总额',
      formula: 'sum(amount)',
      description: '成交额口径',
      status: 'draft',
    })

    const audit = await governanceApi.listAudit(1)
    expect(calls.at(-1)?.[0]).toBe('/api/v1/rebuild/governance/projects/1/audit?page=1&page_size=50')
    expect(audit.list[0]).toMatchObject({ id: 1, actorId: 2, action: 'create', resourceType: 'standard', resourceId: '9' })
  })

  it('preserves 4041/4103 business codes for governance write surface', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => envelope(null, 4103, 'invalid input')))
    await expect(governanceApi.createStandard(1, { code: 'X', name: 'n', dataType: 'decimal' })).rejects.toMatchObject({ code: 4103 })
  })
})

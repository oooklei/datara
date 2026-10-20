/**
 * R8-B 契约测试（node 环境，纯契约层无组件挂载）— P1-0 步骤 4 假 Agent（无 LLM mock 模式）先绿。
 * 断言面：
 *   1. R8-A 工具名单/上下文类型冻结（契约 v1 §2.2）；GREEN 工厂返回真实 API 调用方法；
 *   2. mock 注册表 8 条目（§2.4/§6 数值）与 PoC 启用面（三工具 enabled，五工具 TOOL_DISABLED）；
 *   3. 无 LLM 全链路绿：NL → generate_sql →（授权确认，UI 闸）→ validate_sql → run_sql → 结果+解释；
 *   4. 错误映射（§5 词形：TOOL_NOT_FOUND/TOOL_VERSION_MISMATCH/TOOL_DISABLED/INVALID_PARAMS/BUDGET_EXCEEDED/NOT_FOUND）；
 *   5. 预算拦截（§6：row_limit≤1000、limit≤100、timeout≤30000）；
 *   6. 审计回链（§4：audit_id 回显 + 字段齐备 + 成功失败均落）。
 * 隔离于 K1：零 LLM、零网络（无 fetch stub）。
 */
import { describe, expect, it } from 'vitest'
import {
  R8A_CONTEXT_TYPES,
  R8A_CONTRACT_METHODS,
  R8A_ERROR_CODES,
  R8A_TOOLS,
  R8A_TOOL_VERSION,
  createAiToolsContract,
} from '../../../../services/rebuild/aiToolsApi'
import {
  MOCK_SOVEREIGNTY_CONTEXT_MISSING,
  createMockAgent,
  generateSqlMock,
  mockRegistry,
} from './mockAgent'

const PAGE_CONTEXT = { contextType: 'SQL' as const, contextRef: { project_id: 1, table_name: 'dw.dim_customer' } }
const CTX = { userId: 'user-trae', roles: ['DEVELOPER'] }

function callId(seq: number): string {
  return `tc-test-${String(seq).padStart(4, '0')}`
}

/* ---------- 1. 冻结面与 RED 工厂 ---------- */

describe('R8-A contract freeze surface', () => {
  it('tool list is frozen to the eight tools in contract order', () => {
    expect(R8A_TOOLS).toHaveLength(8)
    expect([...R8A_TOOLS]).toEqual([
      'search_schema',
      'validate_sql',
      'run_sql',
      'get_workflow',
      'validate_workflow',
      'inspect_workflow_run',
      'get_task_metrics',
      'get_lineage',
    ])
  })

  it('context types cover the ten page contexts and error codes cover the frozen space', () => {
    expect(R8A_CONTEXT_TYPES).toHaveLength(10)
    expect(R8A_ERROR_CODES).toHaveLength(12)
  })

  it('contract method list covers registry discovery plus eight tools', () => {
    expect(R8A_CONTRACT_METHODS).toHaveLength(9)
  })

  it('every GREEN contract method is a function (real API call wired)', () => {
    const contract = createAiToolsContract()
    for (const m of R8A_CONTRACT_METHODS) {
      const fn = contract[m]
      expect(typeof fn).toBe('function')
    }
  })
})

/* ---------- 2. mock 注册表 ---------- */

describe('mock registry (§2.4/§6 v1 numbers)', () => {
  it('exposes eight entries at version 1 with PoC minimal enablement', () => {
    const registry = mockRegistry()
    expect(registry).toHaveLength(8)
    expect(registry.map((e) => e.name)).toEqual([...R8A_TOOLS])
    for (const entry of registry) {
      expect(entry.version).toBe(R8A_TOOL_VERSION)
    }
    expect(registry.filter((e) => e.enabled).map((e) => e.name)).toEqual(['search_schema', 'validate_sql', 'run_sql'])
  })

  it('keeps frozen timeout/budget numbers for the PoC tools', () => {
    const byName = new Map(mockRegistry().map((e) => [e.name, e]))
    expect(byName.get('run_sql')?.timeoutMs).toBe(30000)
    expect(byName.get('run_sql')?.retryPolicy.maxAttempts).toBe(1)
    expect(byName.get('search_schema')?.timeoutMs).toBe(10000)
    expect(byName.get('search_schema')?.retryPolicy).toEqual({ maxAttempts: 2, backoffMs: 500 })
  })
})

/* ---------- 3. 无 LLM 全链路绿 ---------- */

describe('mock agent full chain without LLM (isolated from K1)', () => {
  it('NL → generate_sql → (authorization gate) → validate_sql → run_sql → result + explanation', async () => {
    const agent = createMockAgent()

    // 生成 SQL（无 LLM 规则式；主权镜像：上下文缺失即抛）
    const generated = generateSqlMock('查询客户表的数据', PAGE_CONTEXT, CTX.userId)
    expect(generated.sql).toBe('SELECT * FROM dw.dim_customer LIMIT 200')
    expect(generated.explanation).not.toBe('')

    // 授权确认（UI 闸）：测试页仅在用户勾选确认后调用 run_sql——此处模拟已确认后的信封调用
    const validated = await agent.call(
      { toolCallId: callId(1), tool: 'validate_sql', toolVersion: R8A_TOOL_VERSION, params: { project_id: 1, datasource_id: 'ds-1', sql: generated.sql }, pageContext: PAGE_CONTEXT },
      CTX,
    )
    expect(validated.status).toBe('SUCCESS')
    expect(validated.result).toMatchObject({ valid: true, issues: [] })

    const executed = await agent.call(
      { toolCallId: callId(2), tool: 'run_sql', toolVersion: R8A_TOOL_VERSION, params: { project_id: 1, datasource_id: 'ds-1', sql: generated.sql }, pageContext: PAGE_CONTEXT },
      CTX,
    )
    expect(executed.status).toBe('SUCCESS')
    expect(executed.result).toMatchObject({ rowCount: 2, truncated: false })
    expect((executed.result?.['columns'] as unknown[])[0]).toMatchObject({ name: 'customer_id', type: 'BIGINT' })
    expect(executed.result?.['sqlStatementDigest']).toBeTruthy()

    // 结果展示+解释：页面将 rowCount/列/截断与 generate_sql 解释一并呈现（本断言锚定数据可得性）
    expect(generated.explanation).toContain('dim_customer')
  })

  it('sovereignty mirror: generate_sql without explicit user/project context throws', () => {
    expect(() => generateSqlMock('查询数据', null, CTX.userId)).toThrow(MOCK_SOVEREIGNTY_CONTEXT_MISSING)
    expect(() => generateSqlMock('查询数据', PAGE_CONTEXT, '')).toThrow(MOCK_SOVEREIGNTY_CONTEXT_MISSING)
    expect(() => generateSqlMock('查询数据', { contextType: 'SQL', contextRef: { table_name: 't' } }, CTX.userId)).toThrow(
      MOCK_SOVEREIGNTY_CONTEXT_MISSING,
    )
  })

  it('statistical intent maps to COUNT and top intent maps to ordered limit', () => {
    const stats = generateSqlMock('客户表有多少行数据', PAGE_CONTEXT, CTX.userId)
    expect(stats.sql).toBe('SELECT COUNT(*) AS row_count FROM dw.dim_customer')
    const top = generateSqlMock('最近的前 10 条订单表记录', { contextType: 'SQL', contextRef: { project_id: 1, table_name: 'fact_order' } }, CTX.userId)
    expect(top.sql).toBe('SELECT * FROM fact_order ORDER BY 1 DESC LIMIT 10')
  })
})

/* ---------- 4. 错误映射（§5 词形） ---------- */

describe('mock envelope error mapping (§5 frozen words)', () => {
  const agent = createMockAgent()

  it('unknown tool → TOOL_NOT_FOUND', async () => {
    const res = await agent.call(
      { toolCallId: callId(10), tool: 'no_such_tool' as never, toolVersion: R8A_TOOL_VERSION, params: {}, pageContext: null },
      CTX,
    )
    expect(res.status).toBe('ERROR')
    expect(res.error).toMatchObject({ code: 'TOOL_NOT_FOUND', retryable: false })
  })

  it('version drift → TOOL_VERSION_MISMATCH', async () => {
    const res = await agent.call(
      { toolCallId: callId(11), tool: 'run_sql', toolVersion: 2, params: { project_id: 1, datasource_id: 'ds-1', sql: 'SELECT 1' }, pageContext: null },
      CTX,
    )
    expect(res.error?.code).toBe('TOOL_VERSION_MISMATCH')
  })

  it('non-PoC tool → TOOL_DISABLED', async () => {
    const res = await agent.call(
      { toolCallId: callId(12), tool: 'get_workflow', toolVersion: R8A_TOOL_VERSION, params: { project_id: 1, workflow_id: 'wf-1' }, pageContext: null },
      CTX,
    )
    expect(res.error?.code).toBe('TOOL_DISABLED')
  })

  it('missing required param → INVALID_PARAMS', async () => {
    const res = await agent.call(
      { toolCallId: callId(13), tool: 'run_sql', toolVersion: R8A_TOOL_VERSION, params: { project_id: 1, datasource_id: 'ds-1' }, pageContext: null },
      CTX,
    )
    expect(res.error?.code).toBe('INVALID_PARAMS')
  })

  it('unknown datasource → NOT_FOUND', async () => {
    const res = await agent.call(
      { toolCallId: callId(14), tool: 'run_sql', toolVersion: R8A_TOOL_VERSION, params: { project_id: 1, datasource_id: 'ds-404', sql: 'SELECT 1' }, pageContext: null },
      CTX,
    )
    expect(res.error?.code).toBe('NOT_FOUND')
  })
})

/* ---------- 5. 预算拦截（§6） ---------- */

describe('mock budget interception (§6 v1 numbers)', () => {
  const agent = createMockAgent()

  it('run_sql row_limit beyond 1000 → BUDGET_EXCEEDED', async () => {
    const res = await agent.call(
      { toolCallId: callId(20), tool: 'run_sql', toolVersion: R8A_TOOL_VERSION, params: { project_id: 1, datasource_id: 'ds-1', sql: 'SELECT 1', row_limit: 2000 }, pageContext: null },
      CTX,
    )
    expect(res.error?.code).toBe('BUDGET_EXCEEDED')
  })

  it('run_sql timeout_ms beyond 30000 → BUDGET_EXCEEDED', async () => {
    const res = await agent.call(
      { toolCallId: callId(21), tool: 'run_sql', toolVersion: R8A_TOOL_VERSION, params: { project_id: 1, datasource_id: 'ds-1', sql: 'SELECT 1', timeout_ms: 60000 }, pageContext: null },
      CTX,
    )
    expect(res.error?.code).toBe('BUDGET_EXCEEDED')
  })

  it('run_sql timeout_ms may only narrow the budget (converging allowed)', async () => {
    const res = await agent.call(
      { toolCallId: callId(22), tool: 'run_sql', toolVersion: R8A_TOOL_VERSION, params: { project_id: 1, datasource_id: 'ds-1', sql: 'SELECT 1', timeout_ms: 5000 }, pageContext: null },
      CTX,
    )
    expect(res.status).toBe('SUCCESS')
  })
})

/* ---------- 6. 审计回链（§4） ---------- */

describe('mock audit back-link (§4 frozen fields)', () => {
  it('echoes audit_id on the envelope and records success with frozen fields', async () => {
    const agent = createMockAgent()
    const res = await agent.call(
      { toolCallId: callId(30), tool: 'search_schema', toolVersion: R8A_TOOL_VERSION, params: { project_id: 1, keyword: 'order' }, pageContext: PAGE_CONTEXT },
      CTX,
    )
    expect(res.status).toBe('SUCCESS')
    const record = agent.auditRecords().find((r) => r.auditId === res.auditId)
    expect(record).toBeDefined()
    expect(record).toMatchObject({
      toolCallId: callId(30),
      tool: 'search_schema',
      toolVersion: R8A_TOOL_VERSION,
      userId: CTX.userId,
      roles: CTX.roles,
      projectId: 1,
      outcome: 'SUCCESS',
    })
    expect(record?.startedAt).toBeTruthy()
    expect(record?.finishedAt).toBeTruthy()
    // search_schema 预算断言：entries 数计入 budget/refs 语义由 refs 承载（canned 2 表含 order 命中 1 张）
    expect(res.result?.['entries']).toHaveLength(1)
  })

  it('records failures too, with error_code captured', async () => {
    const agent = createMockAgent()
    const res = await agent.call(
      { toolCallId: callId(31), tool: 'get_lineage', toolVersion: R8A_TOOL_VERSION, params: { project_id: 1 }, pageContext: null },
      CTX,
    )
    expect(res.status).toBe('ERROR')
    const record = agent.auditRecords().at(-1)
    expect(record).toMatchObject({ outcome: 'ERROR', errorCode: 'TOOL_DISABLED', toolCallId: callId(31) })
    expect(res.auditId).toBe(record?.auditId)
  })
})

/**
 * AiAssistantPanel 契约测试（增量 18 / R8-A 八工具 UI 接线）。
 *
 * 覆盖场景：
 *   1. 挂载 → FAB 按钮显隐（open=false 默认态）
 *   2. 点击 FAB → 面板展开/收起；close 按钮同效
 *   3. run_sql：参数表单封装 → contract.invoke() 调用；信封 SUCCESS → 结果呈现
 *   4. 注册表动态启停 + 七工具统一参数调用
 *   5. 信封 ERROR → 错误态呈现
 *
 * 测试策略：纯 Vue Test Utils mount + 假契约注入（contractOverride），隔离于真实后端。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AiAssistantPanel from '../AiAssistantPanel.vue'
import { R8A_TOOLS, type R8ARegistryEntry, type R8AToolsContract } from '../../services/rebuild/aiToolsApi'
import type { AiAgentContract } from '../../services/rebuild/aiAgentApi'

function registry(enabled: readonly string[] = R8A_TOOLS): R8ARegistryEntry[] {
  return R8A_TOOLS.map((name) => ({
    name,
    version: 1,
    description: name,
    enabled: enabled.includes(name),
    requiredPermissions: [],
    timeoutMs: 30_000,
    retryPolicy: { maxAttempts: 1, backoffMs: 0 },
    budget: {},
  }))
}

function makeFakeContract(overrides: Partial<R8AToolsContract> = {}): R8AToolsContract {
  return {
    discoverRegistry: vi.fn().mockResolvedValue(registry()),
    searchSchema: vi.fn(),
    validateSql: vi.fn(),
    runSql: vi.fn(),
    getWorkflow: vi.fn(),
    validateWorkflow: vi.fn(),
    inspectWorkflowRun: vi.fn(),
    getTaskMetrics: vi.fn(),
    getLineage: vi.fn(),
    ...overrides,
  }
}

function mountPanel(contract: R8AToolsContract, pageContext?: string | null, agent?: AiAgentContract, projectId?: number) {
  return mount(AiAssistantPanel, {
    props: { contractOverride: contract, agentOverride: agent, projectId, pageContext: pageContext ?? undefined },
    global: { stubs: { teleport: true } },
  })
}

describe('AiAssistantPanel 契约（R8-A 八工具 UI 接线）', () => {
  let fakeContract: R8AToolsContract

  beforeEach(() => { fakeContract = makeFakeContract() })

  describe('挂载与面板显隐', () => {
    it('挂载即显 FAB 按钮，open=false 时面板隐藏', () => {
      const w = mountPanel(fakeContract)
      expect(w.find('[data-ai-fab]').exists()).toBe(true)
      expect(w.find('[data-ai-panel]').exists()).toBe(false)
    })

    it('点击 FAB → 面板展开；再点 → 收起', async () => {
      const w = mountPanel(fakeContract)
      await w.find('[data-ai-fab]').trigger('click')
      expect(w.find('[data-ai-panel]').exists()).toBe(true)
      await w.find('[data-ai-fab]').trigger('click')
      expect(w.find('[data-ai-panel]').exists()).toBe(false)
    })

    it('close 按钮收起面板', async () => {
      const w = mountPanel(fakeContract)
      await w.find('[data-ai-fab]').trigger('click')
      await w.find('[data-ai-close]').trigger('click')
      expect(w.find('[data-ai-panel]').exists()).toBe(false)
    })

    it('open→false 清空 activeTool/result/error', async () => {
      const w = mountPanel(fakeContract)
      await w.find('[data-ai-fab]').trigger('click')
      // 选 run_sql → 填 SQL → 触发错误态
      await w.findAll('[data-tool="run_sql"] button')[0].trigger('click')
      // 不填 SQL，直接关闭
      await w.find('[data-ai-close]').trigger('click')
      // 再打开，activeTool 应为 null（没选中任何工具）
      await w.find('[data-ai-fab]').trigger('click')
      expect(w.find('[data-tool-active="yes"]').exists()).toBe(false)
    })
  })

  describe('run_sql 活接线', () => {
    it('参数封装 → contract.runSql() 调用', async () => {
      const fakeRun = vi.fn().mockResolvedValue({
        executionId: 'ex-1',
        columns: [{ name: 'id', type: 'int' }],
        rows: [[1]],
        rowCount: 1,
        truncated: false,
        durationMs: 42,
        sqlStatementDigest: 'abc',
      })
      const c = makeFakeContract({ runSql: fakeRun })
      const w = mountPanel(c)
      await w.find('[data-ai-fab]').trigger('click')
      await w.findAll('[data-tool="run_sql"] button')[0].trigger('click')

      const sqlInput = w.find('textarea[data-ai-sql-input]')
      await sqlInput.setValue('SELECT 1')
      await w.find('input[data-ai-datasource-id]').setValue(99)
      await w.find('input[data-ai-database]').setValue('testdb')
      await w.find('button[data-ai-run]').trigger('click')

      expect(fakeRun).toHaveBeenCalledWith(
        { sql: 'SELECT 1', datasourceId: 99, database: 'testdb' },
        null,
      )
    })

    it('空 SQL 禁发请求', async () => {
      const fakeRun = vi.fn()
      const c = makeFakeContract({ runSql: fakeRun })
      const w = mountPanel(c)
      await w.find('[data-ai-fab]').trigger('click')
      await w.findAll('[data-tool="run_sql"] button')[0].trigger('click')
      // SQL 空，按钮应 disabled
      expect(w.find('button[data-ai-run]').attributes('disabled')).toBeDefined()
      await w.find('button[data-ai-run]').trigger('click')
      expect(fakeRun).not.toHaveBeenCalled()
    })

    it('信封 SUCCESS → 结果 JSON 呈现', async () => {
      const fakeRun = vi.fn().mockResolvedValue({ rowCount: 7, durationMs: 100 })
      const c = makeFakeContract({ runSql: fakeRun })
      const w = mountPanel(c)
      await w.find('[data-ai-fab]').trigger('click')
      await w.findAll('[data-tool="run_sql"] button')[0].trigger('click')
      await w.find('textarea[data-ai-sql-input]').setValue('SELECT *')
      await w.find('button[data-ai-run]').trigger('click')
      await vi.waitFor(() => expect(w.find('[data-ai-result]').exists()).toBe(true))
      expect(w.find('[data-ai-result]').text()).toContain('rowCount')
    })

    it('信封 ERROR → 错误态呈现', async () => {
      const fakeRun = vi.fn().mockRejectedValue(new Error('EXECUTION_TIMEOUT'))
      const c = makeFakeContract({ runSql: fakeRun })
      const w = mountPanel(c)
      await w.find('[data-ai-fab]').trigger('click')
      await w.findAll('[data-tool="run_sql"] button')[0].trigger('click')
      await w.find('textarea[data-ai-sql-input]').setValue('BAD SQL')
      await w.find('button[data-ai-run]').trigger('click')
      await vi.waitFor(() => expect(w.find('[data-ai-error]').exists()).toBe(true))
      expect(w.find('[data-ai-error]').text()).toContain('EXECUTION_TIMEOUT')
    })
  })

  describe('八工具生产桥接', () => {
    it('按服务端注册表动态启停，不再硬编码仅 run_sql', async () => {
      const c = makeFakeContract({ discoverRegistry: vi.fn().mockResolvedValue(registry(['run_sql', 'search_schema'])) })
      const w = mountPanel(c)
      await w.find('[data-ai-fab]').trigger('click')
      await flushPromises()
      expect(w.find('[data-tool="run_sql"]').attributes('data-tool-enabled')).toBe('yes')
      expect(w.find('[data-tool="search_schema"]').attributes('data-tool-enabled')).toBe('yes')
      expect(w.find('[data-tool="get_lineage"]').attributes('data-tool-enabled')).toBe('no')
      expect(w.find('[data-tool="get_lineage"] .ai-tool-badge').text()).toContain('不可用')
    })

    it('七工具使用契约预置 JSON 参数并调用对应方法', async () => {
      const searchSchema = vi.fn().mockResolvedValue({ entries: [], nextCursor: null })
      const w = mountPanel(makeFakeContract({ searchSchema }))
      await w.find('[data-ai-fab]').trigger('click')
      await flushPromises()
      const item = w.find('[data-tool="search_schema"]')
      await item.find('button').trigger('click')
      expect(item.attributes('data-tool-active')).toBe('yes')
      const input = w.find('textarea[data-ai-json-input]')
      expect(input.element.getAttribute('placeholder')).toContain('project_id')
      await input.setValue('{"project_id":35,"keyword":"orders"}')
      await w.find('button[data-ai-run]').trigger('click')
      await flushPromises()
      expect(searchSchema).toHaveBeenCalledWith({ project_id: 35, keyword: 'orders' }, null)
      expect(w.find('[data-ai-result]').text()).toContain('entries')
    })

    it('非法 JSON 参数在前端拦截，不发送工具请求', async () => {
      const searchSchema = vi.fn()
      const w = mountPanel(makeFakeContract({ searchSchema }))
      await w.find('[data-ai-fab]').trigger('click')
      await flushPromises()
      await w.find('[data-tool="search_schema"] button').trigger('click')
      await w.find('textarea[data-ai-json-input]').setValue('{bad json')
      const run = w.find('button[data-ai-run]')
      expect(run.attributes('disabled')).toBeDefined()
      await run.trigger('click')
      expect(searchSchema).not.toHaveBeenCalled()
    })
  })

  describe('页面上下文', () => {
    it('pageContext 传入时呈现徽标', async () => {
      const w = mountPanel(fakeContract, '/p/12/workflow/edit')
      await w.find('[data-ai-fab]').trigger('click')
      expect(w.find('.ai-context').exists()).toBe(true)
      expect(w.find('.ai-context-value').text()).toBe('/p/12/workflow/edit')
    })

    it('pageContext null 时徽标不呈现', async () => {
      const w = mountPanel(fakeContract, null)
      await w.find('[data-ai-fab]').trigger('click')
      expect(w.find('.ai-context').exists()).toBe(false)
    })
  })

  describe('自然语言 Agent 对话链', () => {
    it('LLM 选择工具后经统一契约执行，再回送工具结果并展示最终回答', async () => {
      const complete = vi.fn()
        .mockResolvedValueOnce({
          message: { role: 'assistant', content: null, toolCalls: [{ id: 'call-1', type: 'function', function: { name: 'search_schema', arguments: '{"project_id":999,"keyword":"order"}' } }] },
          model: 'agent-model', usage: {},
        })
        .mockResolvedValueOnce({ message: { role: 'assistant', content: '找到订单表。' }, model: 'agent-model', usage: {} })
      const searchSchema = vi.fn().mockResolvedValue({ entries: [{ tableName: 'orders' }] })
      const w = mountPanel(makeFakeContract({ searchSchema }), null, { complete }, 35)
      await w.find('[data-ai-fab]').trigger('click')
      await flushPromises()
      await w.find('[data-ai-chat-input]').setValue('查找订单表')
      await w.find('[data-ai-chat-send]').trigger('click')
      await flushPromises()
      await flushPromises()

      expect(searchSchema).toHaveBeenCalledWith({ project_id: 35, keyword: 'order' }, null)
      expect(complete).toHaveBeenCalledTimes(2)
      expect(w.find('[data-ai-chat-transcript]').text()).toContain('search_schema')
      expect(w.find('[data-ai-chat-transcript]').text()).toContain('找到订单表。')
    })
  })
})

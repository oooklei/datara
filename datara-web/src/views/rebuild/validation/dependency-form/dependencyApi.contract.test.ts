/**
 * R4-DEPENDENCY 契约 RED 测试（node 环境，纯契约层无组件挂载）。
 * 断言：方法清单冻结、工厂实现统一抛 R4_DEPENDENCY_NOT_WIRED、
 * 本地表达式草稿拼装行为（组内 join / 组间 AND）。
 * 语义源：客户要求 #5 + 纠偏设计 §5.3（DolphinScheduler 式依赖表单）。
 */
import { describe, expect, it } from 'vitest'
import {
  R4_DEPENDENCY_CONTRACT_METHODS,
  R4_DEPENDENCY_NOT_WIRED,
  composeExpressionDraft,
  createDependencyContract,
  type DependencyGroup,
} from '../../../../services/rebuild/dependencyApi'

const groups: DependencyGroup[] = [
  {
    join: 'OR',
    conditions: [
      { upstreamWorkflowId: 1, dateRange: { periodType: 'day', beginOffset: -1, endOffset: -1 } },
      { upstreamWorkflowId: 2, upstreamTaskCode: 't_load', dateRange: { periodType: 'hour', beginOffset: -2, endOffset: -1 } },
    ],
  },
  {
    join: 'AND',
    conditions: [{ upstreamWorkflowId: 3, dateRange: { periodType: 'week', beginOffset: -1, endOffset: 0 } }],
  },
]

describe('R4 dependencyApi contract (RED)', () => {
  it('contract method list is frozen to the dependency form subset', () => {
    expect(R4_DEPENDENCY_CONTRACT_METHODS).toHaveLength(5)
    expect(R4_DEPENDENCY_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'listCandidateWorkflows',
        'listWorkflowTasks',
        'previewExpression',
        'saveDependency',
        'evaluateDependency',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createDependencyContract()
    for (const method of R4_DEPENDENCY_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

  it('every I/O method refuses until dependency backend is wired', async () => {
    const contract = createDependencyContract()
    const cases: Promise<unknown>[] = [
      contract.listCandidateWorkflows(1),
      contract.listWorkflowTasks(1, 1),
      contract.previewExpression(1, 1, 1, 'task', groups),
      contract.saveDependency({ projectId: 1, workflowId: 1, workflowVersion: 1, taskId: 'task', groups }),
      contract.evaluateDependency({ projectId: 1, workflowId: 1, workflowVersion: 1, taskId: 'task', groups }),
    ]
    for (const p of cases) {
      await expect(p).rejects.toThrow(R4_DEPENDENCY_NOT_WIRED)
    }
  })

  it('composeExpressionDraft joins conditions in-group and groups with AND', () => {
    const draft = composeExpressionDraft(groups)
    expect(draft).toBe(
      '(wf(1) day[-1..-1] OR wf(2) task(t_load) hour[-2..-1]) AND wf(3) week[-1..0]',
    )
  })

  it('composeExpressionDraft keeps single-condition groups unparenthesized', () => {
    const single: DependencyGroup[] = [{ join: 'AND', conditions: [{ upstreamWorkflowId: 7, dateRange: { periodType: 'month', beginOffset: 0, endOffset: 0 } }] }]
    expect(composeExpressionDraft(single)).toBe('wf(7) month[0..0]')
  })
})

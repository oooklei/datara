/**
 * R2 变量契约 RED 测试（node 环境，纯契约层无组件挂载）。
 * 断言：方法清单冻结、工厂实现统一抛 R2_VARIABLE_NOT_WIRED、
 * 七级优先级链为设计真源、本地引用语法解析行为。
 * 语义源：docs/increments/2026-10-14-datara-platform-rebuild-design.md §5。
 */
import { describe, expect, it } from 'vitest'
import {
  R2_VARIABLE_CONTRACT_METHODS,
  R2_VARIABLE_NOT_WIRED,
  VARIABLE_SCOPE_PRIORITY,
  createVariableContract,
  parseVariableReferences,
} from '../../../../services/rebuild/variableApi'

describe('R2 variableApi contract (RED)', () => {
  it('freezes the seven-level priority chain from design section 5', () => {
    expect(VARIABLE_SCOPE_PRIORITY).toEqual(['run', 'task', 'workflow', 'project', 'global', 'env', 'builtin'])
  })

  it('contract method list is frozen to the variable service subset', () => {
    expect(R2_VARIABLE_CONTRACT_METHODS).toHaveLength(6)
    expect(R2_VARIABLE_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'listVariables',
        'saveVariable',
        'completeVariables',
        'checkReference',
        'previewResolution',
        'getRunSnapshot',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createVariableContract()
    for (const method of R2_VARIABLE_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

  it('every I/O method refuses until variable backend is wired', async () => {
    const contract = createVariableContract()
    const cases: Promise<unknown>[] = [
      contract.listVariables(1),
      contract.saveVariable(1, { scope: 'global', name: 'region', valueType: 'string', value: 'cn' }),
      contract.completeVariables('reg', { projectId: 1 }),
      contract.checkReference('${global.region}', { projectId: 1 }),
      contract.previewResolution('${global.region}', { projectId: 1 }),
      contract.getRunSnapshot(1, 1),
    ]
    for (const p of cases) {
      await expect(p).rejects.toThrow(R2_VARIABLE_NOT_WIRED)
    }
  })
})

describe('parseVariableReferences (local pure fn)', () => {
  it('extracts refs, time expressions, and dedupes repeated refs', () => {
    const parsed = parseVariableReferences('a ${global.region} b ${run.dt} c ${global.region} d $[yyyy-MM-dd]')
    expect(parsed.refs).toEqual([
      { scope: 'global', name: 'region' },
      { scope: 'run', name: 'dt' },
    ])
    expect(parsed.timeExpressions).toEqual(['yyyy-MM-dd'])
    expect(parsed.syntaxErrors).toEqual([])
  })

  it('flags unknown scopes, missing dots, and empty names as syntax errors', () => {
    const parsed = parseVariableReferences('${bogus.x} ${nodot} ${global.}')
    expect(parsed.syntaxErrors).toEqual(['${bogus.x}', '${nodot}', '${global.}'])
  })

  it('returns empty result for plain text', () => {
    expect(parseVariableReferences('no variables here')).toEqual({ refs: [], timeExpressions: [], syntaxErrors: [] })
  })
})

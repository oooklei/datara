import { describe, it, expect } from 'vitest'
import { portTypesMatch, type DataType } from '../portTypes'
import cases from './portTypeCases.json'

const DATA_TYPES: readonly DataType[] = [
  'any', 'string', 'number', 'boolean', 'json',
  'table', 'dataset', 'file', 'stream', 'none',
]

describe('portTypesMatch（方案 §3.1 集合交集规则）', () => {
  it.each(cases.cases as { src: DataType; dst: DataType; expected: boolean }[])(
    '$src -> $dst = $expected', ({ src, dst, expected }) => {
      expect(portTypesMatch(src, dst)).toBe(expected)
    })
  it('契约守卫：用例表 src/dst 均属于 DataType 全集（防 JSON 手误经未知→any 分支因错误原因通过）', () => {
    for (const c of cases.cases) {
      expect(DATA_TYPES, `src=${c.src}`).toContain(c.src)
      expect(DATA_TYPES, `dst=${c.dst}`).toContain(c.dst)
    }
  })
  it('未知类型按 any 处理（旧组件未声明向后兼容）', () => {
    expect(portTypesMatch(undefined, 'table')).toBe(true)
    expect(portTypesMatch('table', undefined)).toBe(true)
  })
})

import { describe, it, expect } from 'vitest'
import { portTypesMatch, type DataType } from '../portTypes'
import cases from './portTypeCases.json'

describe('portTypesMatch（方案 §3.1 集合交集规则）', () => {
  it.each(cases.cases as { src: DataType; dst: DataType; expected: boolean }[])(
    '$src -> $dst = $expected', ({ src, dst, expected }) => {
      expect(portTypesMatch(src, dst)).toBe(expected)
    })
  it('未知类型按 any 处理（旧组件未声明向后兼容）', () => {
    expect(portTypesMatch(undefined as never, 'table')).toBe(true)
    expect(portTypesMatch('table', undefined as never)).toBe(true)
  })
})

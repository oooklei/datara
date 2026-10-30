import { describe, expect, it } from 'vitest'
import { parseCsv } from '../csvParse'

describe('parseCsv（B4-d CSV 导入前端解析）', () => {
  it('splits simple rows and drops blank trailing lines', () => {
    expect(parseCsv('a,b,c\n1,2,3\n')).toEqual([['a', 'b', 'c'], ['1', '2', '3']])
  })

  it('honors quoted fields with commas, escaped quotes and CRLF', () => {
    expect(parseCsv('"x,1","he said ""hi""",z\r\nq,w,r\r\n')).toEqual([
      ['x,1', 'he said "hi"', 'z'],
      ['q', 'w', 'r'],
    ])
  })

  it('keeps quoted newlines inside a field', () => {
    expect(parseCsv('a,"line1\nline2",c\n')).toEqual([['a', 'line1\nline2', 'c']])
  })

  it('skips fully empty rows but keeps single-column rows with content', () => {
    expect(parseCsv('a\n\nb\n')).toEqual([['a'], ['b']])
  })
})

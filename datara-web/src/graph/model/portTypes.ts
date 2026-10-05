/** DataType 体系与端口类型交集匹配（方案 §2.2/§3.1）。纯函数，禁止依赖任何 store/service。 */
export type DataType =
  | 'any' | 'string' | 'number' | 'boolean' | 'json'
  | 'table' | 'dataset' | 'file' | 'stream' | 'none'

/** 兼容矩阵：键=源类型，值=可流入的目标类型集合（dataset→table 可、stream→dataset 不可） */
export const TYPE_COMPAT: Record<Exclude<DataType, 'any' | 'none'>, DataType[]> = {
  string:  ['string'],
  number:  ['number', 'string'],
  boolean: ['boolean'],
  json:    ['json', 'string'],
  table:   ['table', 'dataset', 'json'],
  dataset: ['dataset', 'table', 'json'],
  file:    ['file', 'json'],
  stream:  ['stream'],
}

/** 交集匹配：任一端 any 恒真；任一端 none 恒假；未知类型视为 any（存量旧组件未声明 type） */
export function portTypesMatch(src?: string | null, dst?: string | null): boolean {
  if (!src || !dst || src === 'any' || dst === 'any') return true
  if (src === 'none' || dst === 'none') return false
  const row = (TYPE_COMPAT as Record<string, DataType[] | undefined>)[src]
  return row ? row.includes(dst) : true
}

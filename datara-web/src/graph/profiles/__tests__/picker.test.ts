/**
 * I12 T10 动态控件测试：pickerLogic 纯逻辑（依赖解析 / 级联 options / 写回 / 路径拼接）
 * + datasourceApi / runtime-nodes 新包装（listKafkaTopics / listNodeDir）契约，
 * fetch mock 仿 datasourceApi.test.ts 既有 stub 模式。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  columnsOf, dirCrumbs, dirJoin, pickCfg, resolveDsId, sortByCanvasX,
  tableOptions, tablePickPath, writeTablePick,
} from '../pickerLogic'
import { getDataSourceTree, listKafkaTopics, listNodeDir } from '../../../services/datasourceApi'
import type { DsTree } from '../../../services/datasourceApi'
import type { FieldSchema } from '../types'

const CONN_TREE: DsTree = {
  kind: 'connection',
  databases: [
    { name: 'dw', tables: [{ name: 'ods_order', columns: [{ name: 'id', type: 'int' }, { name: 'amt', type: 'decimal' }] }] },
    { name: 'src', tables: [{ name: 'ods_order', columns: [{ name: 'pk', type: 'bigint' }] }] },
  ],
}

describe('pickCfg 依赖字段约定（FieldSchema.pick 缺省兜底）', () => {
  it('table-picker/field-select 缺省 datasource+table；topic-select 缺省 dsRef；dir-select 缺省 runtimeNode', () => {
    expect(pickCfg({ type: 'table-picker' })).toEqual({
      dsKey: 'datasource', tableKey: 'table', nodeKey: 'runtimeNode', writeAs: 'table',
    })
    expect(pickCfg({ type: 'field-select' }).tableKey).toBe('table')
    expect(pickCfg({ type: 'topic-select' }).dsKey).toBe('dsRef')
    expect(pickCfg({ type: 'dir-select' }).nodeKey).toBe('runtimeNode')
  })

  it('schema.pick 显式覆盖缺省（dsKey/writeAs）', () => {
    const f = { type: 'table-picker', pick: { dsKey: 'writerDs', writeAs: 'schemaTable' } } as unknown as FieldSchema
    const c = pickCfg(f)
    expect(c.dsKey).toBe('writerDs')
    expect(c.writeAs).toBe('schemaTable')
  })
})

describe('ds_id 解析（topic-select 经 dsRef 字段值取 ds_id）', () => {
  const rows = [{ id: 9, name: 'kafka源' }, { id: 2, name: '内置源库' }]
  it('名称命中返回数字 id；未命中/空值返回 null', () => {
    expect(resolveDsId('kafka源', rows)).toBe(9)
    expect(resolveDsId('不存在', rows)).toBeNull()
    expect(resolveDsId('', rows)).toBeNull()
    expect(resolveDsId(undefined, rows)).toBeNull()
  })
})

describe('table-picker 写回与回显（writeAs 缺省纯表名，可配 {schema,table}）', () => {
  it('写回：缺省纯表名；schemaTable 写对象；清空写空串', () => {
    expect(writeTablePick('table', ['dw', 'ods_order'])).toBe('ods_order')
    expect(writeTablePick('schemaTable', ['dw', 'ods_order'])).toEqual({ schema: 'dw', table: 'ods_order' })
    expect(writeTablePick('table', [])).toBe('')
  })

  it('cascader 清空（change payload=null 非数组 → 规整空路径）→ 写回空串，不绕过 requiredMissing 必填闸门', () => {
    expect(writeTablePick('table', null)).toBe('')
    expect(writeTablePick('schemaTable', null)).toBe('')
    expect(writeTablePick('schemaTable', [])).toBe('')
    expect(writeTablePick('schemaTable', ['', ''])).toBe('')
  })

  it('回显路径：对象直取；纯表名反查所属库（重名取首个命中库）', () => {
    expect(tablePickPath({ schema: 'src', table: 'ods_order' }, CONN_TREE)).toEqual(['src', 'ods_order'])
    expect(tablePickPath('ods_order', CONN_TREE)).toEqual(['dw', 'ods_order'])
    expect(tablePickPath('nope', CONN_TREE)).toEqual([])
    expect(tablePickPath('', CONN_TREE)).toEqual([])
  })

  it('级联 options：库→表两级；文件型/空树候选置空（失败态）', () => {
    const opts = tableOptions(CONN_TREE)
    expect(opts[0]).toEqual({
      value: 'dw', label: 'dw',
      children: [{ value: 'ods_order', label: 'ods_order', leaf: true }],
    })
    expect(tableOptions(null)).toEqual([])
    const fileTree: DsTree = { kind: 'file', file: 'a.csv', schema: { columns: [], sampledRows: 0 }, sample: [] }
    expect(tableOptions(fileTree)).toEqual([])
  })
})

describe('field-select 列枚举（来自库表树内联 columns，免二次列请求）', () => {
  it('{schema,table} 精确定位；纯表名检索首个命中库', () => {
    expect(columnsOf(CONN_TREE, { schema: 'src', table: 'ods_order' })).toEqual(['pk'])
    expect(columnsOf(CONN_TREE, 'ods_order')).toEqual(['id', 'amt'])
  })
  it('空表值 / 表不在树中 / 文件型树 → 空数组（失败态候选置空）', () => {
    expect(columnsOf(CONN_TREE, '')).toEqual([])
    expect(columnsOf(CONN_TREE, 'nope')).toEqual([])
    const fileTree: DsTree = { kind: 'file', file: 'a.csv', schema: { columns: [], sampledRows: 0 }, sample: [] }
    expect(columnsOf(fileTree, 'a')).toEqual([])
  })
})

describe('datasourceApi / runtime-nodes 新包装契约（fetch mock 仿 datasourceApi.test.ts）', () => {
  const fetchMock = vi.fn()
  function stubRes(data: unknown, code = 0, msg = '') {
    fetchMock.mockResolvedValueOnce({ json: async () => ({ code, msg, data }) })
  }

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', { getItem: () => 'tok-t10', setItem: vi.fn(), removeItem: vi.fn() })
  })

  it('table-picker 级联调用序：ds 名解析 id 后单次 GET /datasources/{id}/tree（columns 内联，field-select 复用不再发请求）', async () => {
    stubRes(CONN_TREE)
    const dsId = resolveDsId('内置源库', [{ id: 7, name: '内置源库' }])
    expect(dsId).toBe(7)
    const tree = await getDataSourceTree(dsId as number)
    const opts = tableOptions(tree)
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(['/api/v1/datasources/7/tree'])
    expect(opts[0].children?.[0].value).toBe('ods_order')
    expect(columnsOf(tree, 'ods_order')).toEqual(['id', 'amt'])
    expect(fetchMock.mock.calls).toHaveLength(1)
  })

  it('topic-select：经 dsRef 解析 ds_id → GET /datasources/{id}/topics 解包 topics；错误码透传为行内错误语义', async () => {
    stubRes({ topics: ['t-a', 't-b'] })
    const dsId = resolveDsId('kafka源', [{ id: 9, name: 'kafka源' }])
    const topics = await listKafkaTopics(dsId as number)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/datasources/9/topics')
    expect(topics).toEqual(['t-a', 't-b'])

    stubRes(null, 400, '仅 Kafka 数据源支持 topic 枚举')
    await expect(listKafkaTopics(2)).rejects.toThrow('仅 Kafka 数据源支持 topic 枚举')
  })

  it('dir-select 懒加载：缺省无 path 查询串（后端取 runtime_dir）→ 下钻 dirJoin 拼接绝对路径再查', async () => {
    stubRes({ path: '/mnt/lei', entries: [{ name: 'datara', dir: true, size: 0, mtime: 1 }, { name: 'a.csv', dir: false, size: 3, mtime: 2 }] })
    const first = await listNodeDir(3)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/runtime-nodes/3/ls')
    expect(first.path).toBe('/mnt/lei')

    stubRes({ path: '/mnt/lei/datara', entries: [] })
    const next = dirJoin(first.path, 'datara')
    expect(next).toBe('/mnt/lei/datara')
    const second = await listNodeDir(3, next)
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/runtime-nodes/3/ls?path=%2Fmnt%2Flei%2Fdatara')
    expect(second.entries).toEqual([])
  })

  it('dirJoin 根目录不双斜杠；dirCrumbs 面包屑切分与回跳路径', async () => {
    expect(dirJoin('/', 'mnt')).toBe('/mnt')
    expect(dirJoin('/mnt/', 'lei')).toBe('/mnt/lei')
    expect(dirCrumbs('/')).toEqual([{ name: '/', path: '/' }])
    expect(dirCrumbs('/mnt/lei')).toEqual([
      { name: '/', path: '/' },
      { name: 'mnt', path: '/mnt' },
      { name: 'lei', path: '/mnt/lei' },
    ])
  })
})

describe('sortByCanvasX 画布左→右排序（join 键左右候选定位）', () => {
  it('按 position.x 升序重排，连线先后不影响左右语义（I12 评审修）', () => {
    const nodes = [
      { id: 'right', position: { x: 300, y: 0 } },
      { id: 'left', position: { x: 100, y: 0 } },
    ]
    expect(sortByCanvasX(nodes).map((n) => n.id)).toEqual(['left', 'right'])
  })
  it('x 缺失或相等回退原序（稳定，不重排）', () => {
    const missing = [{ id: 'a' }, { id: 'b' }] as { id: string; position?: { x?: number } }[]
    expect(sortByCanvasX(missing).map((n) => n.id)).toEqual(['a', 'b'])
    const same = [
      { id: 'a', position: { x: 100, y: 0 } },
      { id: 'b', position: { x: 100, y: 50 } },
    ]
    expect(sortByCanvasX(same).map((n) => n.id)).toEqual(['a', 'b'])
  })
})

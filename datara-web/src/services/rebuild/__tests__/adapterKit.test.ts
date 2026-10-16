/**
 * adapterKit（FE 契约适配层共享机械原语）单元测试。
 * 覆盖：§2.1 snake↔camel 双向（含嵌套/数组/null/字符串值透传）、§2.2 id 归一双向、
 * §2.4 ContractApiError、R2.3 uuid→number 有损 fail-fast、语义内容不改写、
 * 排除项负面用例（targetWritten 不推导、枚举值词形不映射）。
 */
import { describe, expect, it } from 'vitest'
import {
  ID_NORMALIZATION_FAILED,
  ContractApiError,
  camelToSnake,
  camelToSnakeKey,
  numberToWireId,
  snakeToCamel,
  snakeToCamelKey,
  wireIdToNumber,
  wireIdToString,
} from '../adapterKit'

describe('§2.1 命名映射 snakeToCamelKey（键级）', () => {
  it('纯小写 snake_case 参与转换', () => {
    expect(snakeToCamelKey('rows_read')).toBe('rowsRead')
    expect(snakeToCamelKey('watermark_column')).toBe('watermarkColumn')
    expect(snakeToCamelKey('value_type')).toBe('valueType')
  })

  it('无下划线短键原样（R1.3：db/sql 等）', () => {
    expect(snakeToCamelKey('db')).toBe('db')
    expect(snakeToCamelKey('sql')).toBe('sql')
    expect(snakeToCamelKey('name')).toBe('name')
  })

  it('非标准 snake 键原样返回（R1.4 fail-visible，不猜测词形）', () => {
    expect(snakeToCamelKey('UPPER_SNAKE')).toBe('UPPER_SNAKE')
    expect(snakeToCamelKey('Rows_Read')).toBe('Rows_Read')
    expect(snakeToCamelKey('_leading')).toBe('_leading')
    expect(snakeToCamelKey('trailing_')).toBe('trailing_')
    expect(snakeToCamelKey('double__underscore')).toBe('double__underscore')
  })
})

describe('§2.1 命名映射 camelToSnakeKey（键级）', () => {
  it('标准 camel 边界参与转换', () => {
    expect(camelToSnakeKey('rowsTotal')).toBe('rows_total')
    expect(camelToSnakeKey('idempotencyKey')).toBe('idempotency_key')
    expect(camelToSnakeKey('rowsIn')).toBe('rows_in')
    expect(camelToSnakeKey('targetOrdinal2')).toBe('target_ordinal2')
  })

  it('无边界或缩写词键原样返回（不猜测拆分）', () => {
    expect(camelToSnakeKey('db')).toBe('db')
    expect(camelToSnakeKey('SQLText')).toBe('SQLText')
    expect(camelToSnakeKey('Db')).toBe('Db')
    expect(camelToSnakeKey('rows_total')).toBe('rows_total')
  })
})

describe('§2.1 snakeToCamel（BE→FE 响应方向，深度递归）', () => {
  it('扁平键转换', () => {
    expect(snakeToCamel({ rows_read: 5, rows_inserted: 3, name: 'x' })).toEqual({ rowsRead: 5, rowsInserted: 3, name: 'x' })
  })

  it('嵌套对象与数组递归（R1.2，含数组元素为对象）', () => {
    const wire = {
      plan_id: 7,
      source: { datasource_id: 1, schema: 's', table: 't' },
      candidates: [{ datasource_id: 2, schema: 'a' }, { datasource_id: 3, schema: 'b' }],
    }
    expect(snakeToCamel(wire)).toEqual({
      planId: 7,
      source: { datasourceId: 1, schema: 's', table: 't' },
      candidates: [{ datasourceId: 2, schema: 'a' }, { datasourceId: 3, schema: 'b' }],
    })
  })

  it('最深 3 层递归（StreamObservation.offset.current 深度）', () => {
    expect(snakeToCamel({ level_one: { level_two: { level_three: 1 } } })).toEqual({ levelOne: { levelTwo: { levelThree: 1 } } })
  })

  it('标量数组递归且元素值不变', () => {
    expect(snakeToCamel({ stmt_indexes: [0, 1, 2] })).toEqual({ stmtIndexes: [0, 1, 2] })
  })

  it('null 与 undefined 值保留（键仍转换）', () => {
    const out = snakeToCamel({ precision: null, lower_bound: null, upper_bound: undefined }) as Record<string, unknown>
    expect(out.precision).toBeNull()
    expect(out.lowerBound).toBeNull()
    expect('upperBound' in out).toBe(true)
    expect(out.upperBound).toBeUndefined()
  })

  it('R1.3 字符串值一律原样透传，不做内部转换', () => {
    const out = snakeToCamel({
      checkpoint: 'rows_read=5; rows_inserted=3',
      constantValue: 'replace_table',
      sql_text: 'SELECT a_b FROM t WHERE x = "s_q_l"',
    })
    expect(out.checkpoint).toBe('rows_read=5; rows_inserted=3')
    expect(out.constantValue).toBe('replace_table')
    expect((out as Record<string, unknown>).sqlText).toBe('SELECT a_b FROM t WHERE x = "s_q_l"')
  })

  it('R1.4 非标准键不猜测改写', () => {
    const wire = { UPPER_SNAKE: 1, 'x-y': 2, _lead: 3, Rows_Read: 4 }
    expect(snakeToCamel(wire)).toEqual(wire)
  })

  it('数字/布尔值透传，空对象与空数组保持', () => {
    expect(snakeToCamel({ a_b: 1.5, c_d: true, e: {}, f: [] })).toEqual({ aB: 1.5, cD: true, e: {}, f: [] })
  })

  it('未发生变化的子树按原引用返回（避免不必要对象创建）', () => {
    const alreadyCamel = { mode: 'full', nested: { deep: 1 }, list: [1, 'a', null] }
    expect(snakeToCamel(alreadyCamel)).toBe(alreadyCamel)
  })

  it('顶层标量原样返回', () => {
    expect(snakeToCamel('plain_string')).toBe('plain_string')
    expect(snakeToCamel(42)).toBe(42)
    expect(snakeToCamel(null)).toBeNull()
  })
})

describe('§2.1 camelToSnake（FE→BE 请求方向，深度递归）', () => {
  it('扁平键转换', () => {
    expect(camelToSnake({ planVersion: 2, idempotencyKey: 'k' })).toEqual({ plan_version: 2, idempotency_key: 'k' })
  })

  it('SyncPlanDraft 形态：嵌套对象 + 映射行数组', () => {
    const draft = {
      projectId: 1,
      mode: 'source_table',
      source: { datasourceId: 10, schema: 's', table: 't' },
      mapping: [{ targetOrdinal: 1, operation: 'constant', constantValue: 'replace_table' }],
    }
    expect(camelToSnake(draft)).toEqual({
      project_id: 1,
      mode: 'source_table',
      source: { datasource_id: 10, schema: 's', table: 't' },
      mapping: [{ target_ordinal: 1, operation: 'constant', constant_value: 'replace_table' }],
    })
  })

  it('R1.3 字符串值透传：枚举值 replace_table / 含下划线列名不改写', () => {
    const out = camelToSnake({ writeMode: 'replace_table', watermarkColumn: 'created_at' })
    expect(out).toEqual({ write_mode: 'replace_table', watermark_column: 'created_at' })
  })

  it('null/undefined/数组元素值形态不变', () => {
    const out = camelToSnake({ lowerBound: null, upperBound: undefined, list: ['x_y', 2] })
    expect(out).toEqual({ lower_bound: null, upper_bound: undefined, list: ['x_y', 2] })
  })

  it('未发生变化的子树按原引用返回', () => {
    const alreadySnake = { rows_total: 5, db: 'x' }
    expect(camelToSnake(alreadySnake)).toBe(alreadySnake)
  })
})

describe('§2.1 双向 round-trip 与语义内容不改写', () => {
  it('camelToSnake(snakeToCamel(wire)) === wire（键名级无损往返）', () => {
    const wire = {
      plan_id: 7,
      rows_read: 10,
      rows_inserted: 7,
      rows_updated: 2,
      rows_rejected: 1,
      status: 'cancel_requested',
      source: { datasource_id: 1, table: 't' },
      attempts: [{ attempt_id: 1, started_at: '2026-10-16T00:00:00Z' }],
    }
    expect(camelToSnake(snakeToCamel(wire))).toEqual(wire)
  })

  it('snakeToCamel(camelToSnake(request)) === request', () => {
    const request = { projectId: 1, planId: 2, planVersion: 3, planDigest: 'abc', idempotencyKey: 'k' }
    expect(snakeToCamel(camelToSnake(request))).toEqual(request)
  })

  it('仅键名变化，全部值深度不变（语义内容不改写）', () => {
    const wire = { rows_read: 10, rows_inserted: 7, rows_updated: 2, status: 'cancel_requested', checkpoint: 'opaque_x_y' }
    const out = snakeToCamel(wire) as Record<string, unknown>
    expect(out.rowsRead).toBe(10)
    expect(out.rowsInserted).toBe(7)
    expect(out.rowsUpdated).toBe(2)
    expect(out.status).toBe('cancel_requested')
    expect(out.checkpoint).toBe('opaque_x_y')
  })

  it('负面：adapter 不做计数推导——targetWritten 不被合成（挂 R4-SYNC Q7）', () => {
    const wire = { rows_inserted: 3, rows_updated: 2 }
    const out = snakeToCamel(wire) as Record<string, unknown>
    // 通用机械映射仅做词形转换（rows_inserted → rowsInserted）；rows_inserted → inserted、
    // rows_read → sourceRead 等字段级键对应属 R1.1 每 API 文件映射表（GREEN 接线期登记），非本原语职责
    expect(out.rowsInserted).toBe(3)
    expect(out.rowsUpdated).toBe(2)
    expect('targetWritten' in out).toBe(false)
    expect(out.targetWritten).toBeUndefined()
  })

  it('负面：wire 显式携带 target_written 时仅机械换键，值原样透传不重算', () => {
    const wire = { rows_inserted: 3, rows_updated: 2, target_written: 999 }
    const out = snakeToCamel(wire) as Record<string, unknown>
    expect(out.targetWritten).toBe(999) // 不被改写为 3+2=5
    expect(out.rowsInserted).toBe(3)
    expect(out.rowsUpdated).toBe(2)
  })

  it('负面：adapter 不做枚举值词形映射——cancel_requested 原样透传（Q9 已裁定词形落契约/页面层）', () => {
    const wire = { status: 'cancel_requested' }
    const out = snakeToCamel(wire) as Record<string, unknown>
    expect(out.status).toBe('cancel_requested')
  })
})

describe('§2.2 wireIdToNumber（wire → FE number，R2.3 有损即拒绝）', () => {
  it('纯十进制整数字符串无损转换', () => {
    expect(wireIdToNumber('42', 'planId')).toBe(42)
    expect(wireIdToNumber('0', 'runId')).toBe(0)
    expect(wireIdToNumber('9007199254740991', 'planId')).toBe(9007199254740991)
  })

  it('wire 已是安全整数 number 时直接返回', () => {
    expect(wireIdToNumber(42, 'planId')).toBe(42)
    expect(wireIdToNumber(0, 'runId')).toBe(0)
  })

  it('允许负整数字面量（无损往返）', () => {
    expect(wireIdToNumber('-5', 'planId')).toBe(-5)
  })

  it('uuid→number 有损情形 fail-fast（R2.3：抛 ContractApiError，绝不静默截断）', () => {
    const uuid = '3f2a7c9e-8b1d-4c2a-9e6f-0a1b2c3d4e5f'
    let caught: unknown
    try {
      wireIdToNumber(uuid, 'planId')
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(ContractApiError)
    const err = caught as ContractApiError
    expect(err.code).toBe(ID_NORMALIZATION_FAILED)
    expect(err.httpStatus).toBe(0)
    expect(err.msg).toContain('planId')
    expect(err.raw).toBe(uuid)
  })

  it('非法/有损字符串字面量全部拒绝：十六进制、指数、空白、前导零、小数、-0', () => {
    const cases = ['abc', '', ' 42', '42 ', '0x1F', '1e3', '007', '-007', '-0', '2.5', '+5', '１２３']
    for (const value of cases) {
      expect(() => wireIdToNumber(value, 'planId'), `input: ${JSON.stringify(value)}`).toThrow(ContractApiError)
    }
  })

  it('超出安全整数范围（string 与 number 双形态）拒绝', () => {
    expect(() => wireIdToNumber('9007199254740992', 'planId')).toThrow(ContractApiError)
    expect(() => wireIdToNumber(Number.MAX_SAFE_INTEGER + 1, 'planId')).toThrow(ContractApiError)
  })

  it('非整数 number 与非原始类型拒绝', () => {
    expect(() => wireIdToNumber(1.5, 'planId')).toThrow(ContractApiError)
    expect(() => wireIdToNumber(NaN, 'planId')).toThrow(ContractApiError)
    expect(() => wireIdToNumber(Infinity, 'planId')).toThrow(ContractApiError)
    expect(() => wireIdToNumber(null, 'planId')).toThrow(ContractApiError)
    expect(() => wireIdToNumber(undefined, 'planId')).toThrow(ContractApiError)
    expect(() => wireIdToNumber({ id: 1 }, 'planId')).toThrow(ContractApiError)
    expect(() => wireIdToNumber([42], 'planId')).toThrow(ContractApiError)
  })
})

describe('§2.2 numberToWireId（FE number → wire string，R2.2 无损正向）', () => {
  it('安全整数序列化', () => {
    expect(numberToWireId(42, 'planId')).toBe('42')
    expect(numberToWireId(0, 'runId')).toBe('0')
    expect(numberToWireId(-5, 'planId')).toBe('-5')
  })

  it('非安全整数 fail-fast', () => {
    expect(() => numberToWireId(1.5, 'planId')).toThrow(ContractApiError)
    expect(() => numberToWireId(NaN, 'planId')).toThrow(ContractApiError)
    expect(() => numberToWireId(Infinity, 'planId')).toThrow(ContractApiError)
    expect(() => numberToWireId(Number.MAX_SAFE_INTEGER + 1, 'planId')).toThrow(ContractApiError)
  })
})

describe('§2.2 wireIdToString（wire → FE string id，透传校验）', () => {
  it('字符串 id 原样透传（uuid / run_id / job_id，不 trim 不改写）', () => {
    expect(wireIdToString('3f2a7c9e-8b1d-4c2a-9e6f-0a1b2c3d4e5f', 'runId')).toBe('3f2a7c9e-8b1d-4c2a-9e6f-0a1b2c3d4e5f')
    expect(wireIdToString('run-abc_123', 'runId')).toBe('run-abc_123')
    expect(wireIdToString(' job-1 ', 'jobId')).toBe(' job-1 ')
  })

  it('空字符串拒绝（fail-visible）', () => {
    expect(() => wireIdToString('', 'runId')).toThrow(ContractApiError)
  })

  it('BE 以 JSON number 下发数值 id 时无损转 string', () => {
    expect(wireIdToString(42, 'jobId')).toBe('42')
    expect(() => wireIdToString(1.5, 'jobId')).toThrow(ContractApiError)
  })

  it('其他类型拒绝', () => {
    expect(() => wireIdToString(null, 'jobId')).toThrow(ContractApiError)
    expect(() => wireIdToString(undefined, 'jobId')).toThrow(ContractApiError)
    expect(() => wireIdToString({ id: 'x' }, 'jobId')).toThrow(ContractApiError)
  })
})

describe('§2.4 ContractApiError（R4.1 归一错误类型）', () => {
  it('承载 httpStatus/code/msg/raw 并保持 Error 语义', () => {
    const raw = { code: 4001, msg: 'bad request' }
    const err = new ContractApiError({ httpStatus: 400, code: 4001, msg: 'variable save failed', raw })
    expect(err).toBeInstanceOf(Error)
    expect(err).toBeInstanceOf(ContractApiError)
    expect(err.name).toBe('ContractApiError')
    expect(err.message).toBe('variable save failed')
    expect(err.httpStatus).toBe(400)
    expect(err.code).toBe(4001)
    expect(err.msg).toBe('variable save failed')
    expect(err.raw).toBe(raw)
  })

  it('code 支持适配层本地字符串错误码', () => {
    const err = new ContractApiError({ httpStatus: 0, code: ID_NORMALIZATION_FAILED, msg: 'x' })
    expect(err.code).toBe('ID_NORMALIZATION_FAILED')
  })

  it('未传 raw 时 raw 值为 undefined（useDefineForClassFields 下声明字段被 define，以值判别）', () => {
    const err = new ContractApiError({ httpStatus: 503, code: 5031, msg: 'runtime unavailable' })
    expect(err.raw).toBeUndefined()
  })

  it('id 归一错误统一以 rejected promise 形态可用（async 契约方法形态一致）', async () => {
    await expect(Promise.resolve().then(() => wireIdToNumber('not-a-number', 'runId'))).rejects.toBeInstanceOf(ContractApiError)
  })
})

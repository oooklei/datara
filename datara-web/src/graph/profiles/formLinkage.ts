/**
 * I4 表单联动纯函数（§9）：C22 来源模式切换清空对方参数 + ${tmp.*} 前端侧引用提示。
 * 与组件解耦（不引 .vue），供 dag.ts 表单 schema 与 vitest 直接复用；
 * TMP_NAME_OK 对齐 worker 侧 common/tmpdata.TMP_NAME_RE（^[a-z][a-z0-9_]{2,31}$）。
 */
import type { NodeSchema } from './types'

/** 临时数据名合法规则（与后端 TMP_NAME_RE 同口径） */
export const TMP_NAME_OK = /^[a-z][a-z0-9_]{2,31}$/

/**
 * C22 来源模式切换联动：清空对方侧参数（设计 §9 表单控件联动）。
 * - 切到 manual（手动参数）→ 清空数据源引用
 * - 切到 datasource（数据源中心文件源）→ 清空路径/格式/编码/分隔符/表头/sheet
 */
export function c22OnModeChange(data: Record<string, unknown>, mode: unknown): void {
  if (mode === 'manual') {
    data.datasource = ''
  } else {
    data.path = ''
    data.format = ''
    data.encoding = ''
    data.delimiter = ''
    data.header = false
    data.sheet = ''
  }
}

/** ${tmp.<name>} 引用是否可用：已勾选注册且命名合法（键为 tmpName，避免与节点显示名 data.name 冲突） */
export function tmpRefUsable(data: Record<string, unknown>): boolean {
  return !!data.register && TMP_NAME_OK.test(String(data.tmpName ?? ''))
}

/** ${tmp.*} 引用提示文案：可用返回空串，否则给出不可用原因 */
export function tmpRefHint(data: Record<string, unknown>): string {
  if (!data.register) return '未注册临时数据：下游 ${tmp.*} 引用不可用，仅产出行数统计'
  const name = String(data.tmpName ?? '')
  if (!TMP_NAME_OK.test(name)) return '临时数据名未配置或不合法（需小写字母开头，3~32 位 a-z0-9_）：${tmp.*} 引用暂不可用'
  return ''
}

/**
 * 必填完整性检查（W1 流节点配置闭环）：返回当前分型下缺失的必填字段 label 清单。
 * 判定口径：required 且 showIf(data) 通过且值为空（''/null/undefined/空数组）。
 * 三处共用同一判定：画布节点「未配置」角标 / 校验面板 / Inspector 必填红星。
 */
export function requiredMissing(schema: NodeSchema, data: Record<string, unknown>): string[] {
  return (schema.form ?? [])
    .filter((f) => f.required && f.type !== 'hint' && (!f.showIf || f.showIf(data)))
    .filter((f) => {
      const v = data[f.key]
      if (Array.isArray(v)) return v.length === 0
      return v === undefined || v === null || v === ''
    })
    .map((f) => f.label || f.key)
}

/* ================= I6 C17 数据同步联动（设计 §9：读端类型切换 + SQL 预览） ================= */

/** C17 读端是否连接型（mysql/greatdb） */
export function c17IsConnReader(d: Record<string, unknown>): boolean {
  return ['mysql', 'greatdb'].includes(String(d.readerType ?? 'mysql'))
}

/** C17 读端是否文件型（csv/txt/excel） */
export function c17IsFileReader(d: Record<string, unknown>): boolean {
  return ['csv', 'txt', 'excel'].includes(String(d.readerType ?? ''))
}

/**
 * C17 读端类型切换联动（设计 §9）：清空对侧参数。
 * - 切连接型 → 清空文件参数
 * - 切文件型 → 清空数据源/表名/schema 集/增量条件（文件源无 schema 概念）
 */
export function c17OnReaderTypeChange(data: Record<string, unknown>, value: unknown): void {
  if (c17IsConnReader({ readerType: value })) {
    data.readerPath = ''
    data.readerSheet = ''
  } else {
    data.readerDs = ''
    data.readerTable = ''
    data.readerSchemasText = ''
    data.autoSchema = true
    data.incrementalColumn = ''
    data.incrementalExpr = ''
  }
}

/**
 * C17 union/src_flag 分支 SQL 预览（变量未解析形态，设计 §5 标识列附加预览）。
 * 单 schema/未填表名返回单语句；多 schema 按 strategy 生成 UNION ALL；增量列附 WHERE 形态示意。
 */
export function c17SqlPreview(d: Record<string, unknown>): string {
  if (!c17IsConnReader(d)) return ''
  const table = String(d.readerTable ?? '').trim()
  if (!table) return ''
  const schemas = String(d.readerSchemasText ?? '')
    .split(/[,，]/).map((s) => s.trim()).filter(Boolean)
  if (!schemas.length) return `SELECT * FROM \`${table}\``
  const flag = String(d.flagColumn ?? 'src_schema')
  const branches = schemas.map((s) =>
    d.strategy === 'src_flag'
      ? `SELECT *, '${s}' AS \`${flag}\` FROM \`${s}\`.\`${table}\``
      : `SELECT * FROM \`${s}\`.\`${table}\``,
  )
  let sql = branches.join('\n  UNION ALL\n')
  const inc = String(d.incrementalColumn ?? '').trim()
  if (inc) sql = `SELECT * FROM (\n  ${sql}\n) t WHERE \`${inc}\` > ${String(d.incrementalExpr ?? '?')}`
  return sql
}

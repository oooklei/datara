/**
 * M15 数据安全 · 脱敏工具（列级权限的展示层落地）。
 * 策略对齐需求：掩码/替换/哈希；sample 预览按字段名+值形态自动识别敏感类型。
 */

/** 姓名替换：保留姓，其余打星 */
export function maskName(v: string): string {
  if (!v) return v
  return v[0] + '*'.repeat(Math.max(v.length - 1, 1))
}

/** 手机号：138****1234 */
export function maskPhone(v: string): string {
  const d = v.replace(/\D/g, '')
  return d.length === 11 ? d.slice(0, 3) + '****' + d.slice(7) : v
}

/** 身份证：保留前6后4 */
export function maskIdCard(v: string): string {
  const d = v.replace(/\s/g, '')
  return d.length >= 15 ? d.slice(0, 6) + '********' + d.slice(-4) : v
}

/** 银行卡：仅保留后4位 */
export function maskBankCard(v: string): string {
  const d = v.replace(/\D/g, '')
  return d.length >= 12 ? '************' + d.slice(-4) : v
}

/** 敏感字段名 → 类型（需求：基于正则规则 + 字段名） */
export function sniffType(field: string): string | null {
  const f = field.toLowerCase()
  if (/phone|mobile|tel/.test(f)) return '手机号'
  if (/idcard|id_card|cert_no|identity/.test(f)) return '身份证号'
  if (/bank|card_no|acct/.test(f)) return '银行卡号'
  if (/user_name|realname|name$/.test(f) && !/org|table|file/.test(f)) return '姓名'
  return null
}

/** 按类型脱敏一个值 */
export function maskByType(type: string, v: unknown): unknown {
  if (typeof v !== 'string') return v
  switch (type) {
    case '手机号': return maskPhone(v)
    case '身份证号': return maskIdCard(v)
    case '银行卡号': return maskBankCard(v)
    case '姓名': return maskName(v)
    default: return v
  }
}

/**
 * sample 行预览自动脱敏：字段名命中敏感规则（enabled）即脱敏；
 * 未命中字段名但值形态像手机号/证件号时兜底脱敏。
 */
export function maskRow(
  row: Record<string, unknown>,
  rules: { field: string; type: string; enabled: boolean }[],
): Record<string, unknown> {
  const byField = new Map(rules.filter((r) => r.enabled).map((r) => [r.field.toLowerCase(), r.type]))
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(row)) {
    const t = byField.get(k.toLowerCase()) ?? sniffType(k)
    if (t && typeof v === 'string') { out[k] = maskByType(t, v); continue }
    // 值形态兜底：11 位手机号 / 18 位身份证
    if (typeof v === 'string' && /^1\d{10}$/.test(v)) { out[k] = maskPhone(v); continue }
    if (typeof v === 'string' && /^\d{17}[\dXx]$/.test(v)) { out[k] = maskIdCard(v); continue }
    out[k] = v
  }
  return out
}

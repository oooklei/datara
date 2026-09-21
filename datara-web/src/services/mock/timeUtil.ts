/**
 * 本地时间格式化：输出 'YYYY-MM-DD HH:mm'（与 seed.updatedAt 格式一致）。
 * 替代 toISOString()（UTC，会比本地时间早 8 小时）。
 */
export function localTime(d: Date = new Date()): string {
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

/**
 * RFC 4180 感知的 CSV 解析（双引号包裹、双写转义、CRLF）。
 * CsvImportDialog 用它在前端完成解析（B4-d 契约统一 JSON body，不走 multipart）。
 */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false
  let i = 0
  while (i < text.length) {
    const ch = text[i]
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue }
        inQuotes = false; i += 1; continue
      }
      field += ch; i += 1; continue
    }
    if (ch === '"') { inQuotes = true; i += 1; continue }
    if (ch === ',') { row.push(field); field = ''; i += 1; continue }
    if (ch === '\r') { i += 1; continue }
    if (ch === '\n') { row.push(field); rows.push(row); row = []; field = ''; i += 1; continue }
    field += ch; i += 1
  }
  if (field !== '' || row.length > 0) { row.push(field); rows.push(row) }
  return rows.filter((r) => r.length > 1 || (r[0] ?? '') !== '')
}

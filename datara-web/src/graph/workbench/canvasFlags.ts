/**
 * Task 12（§3.6）画布渲染开关：localStorage 轻量持久化（键 datara.wb.flags）。
 * 视口裁剪默认开启；个别环境如出现渲染异常，可手动写入
 * localStorage.setItem('datara.wb.flags', '{"canvasOnlyRenderVisible":false}') 关闭排查。
 */
const KEY = 'datara.wb.flags'

/** 视口裁剪开关（默认 on，localStorage datara.wb.flags 持久化，可手动关闭排查渲染问题） */
export function canvasOnlyRenderVisible(): boolean {
  try {
    return (JSON.parse(localStorage.getItem(KEY) ?? '{}') as { canvasOnlyRenderVisible?: boolean })
      .canvasOnlyRenderVisible !== false
  } catch {
    return true
  }
}

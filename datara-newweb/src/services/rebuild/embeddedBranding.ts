/**
 * 客户观摩模式的嵌入页面文案收口：实现组件仍可保留内部标识，
 * 但用户可见文本统一使用平台业务名称，不泄漏底层产品名。
 */
const REPLACEMENTS: Array<[RegExp, string]> = [
  [/dolphinscheduler/gi, '任务运行底座'],
  [/dbx/gi, '数据开发工具'],
  [/海豚/g, '任务运行底座'],
]

function sanitize(value: string): string {
  return REPLACEMENTS.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), value)
}

function visit(node: Node): void {
  if (node.nodeType === Node.TEXT_NODE) {
    const current = node.nodeValue ?? ''
    const next = sanitize(current)
    if (next !== current) node.nodeValue = next
    return
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return
  const element = node as Element
  for (const attribute of ['title', 'aria-label']) {
    const current = element.getAttribute(attribute)
    if (current !== null) {
      const next = sanitize(current)
      if (next !== current) element.setAttribute(attribute, next)
    }
  }
  node.childNodes.forEach(visit)
}

/** Returns a disposer for the mutation observer. */
export function sanitizeEmbeddedBranding(document: Document): () => void {
  visit(document.documentElement)
  const observer = new MutationObserver((records) => {
    records.forEach((record) => record.addedNodes.forEach(visit))
  })
  observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true })
  return () => observer.disconnect()
}

/**
 * 观摩态隐藏 dbx 欢迎页「AI 编程助手集成」推广卡：dbx 属外链独立产品，
 * 嵌入态不重复推广其 MCP 外部集成入口。以卡片内唯一的 `npx @dbx-app/mcp-server`
 * 命令文本为锚点（不随界面语言与 Tailwind 类名变化），隐藏其 `rounded-lg border` 卡片容器。
 */
export function hideEmbeddedMcpPromoCard(document: Document): () => void {
  const hide = (root: Document | Element): void => {
    const codes = root instanceof Element && root.matches('code')
      ? [root, ...root.querySelectorAll('code')]
      : root.querySelectorAll('code')
    for (const code of codes) {
      if (!(code.textContent ?? '').includes('@dbx-app/mcp-server')) continue
      let el: HTMLElement | null = code.parentElement
      while (el !== null && el !== document.body) {
        if (el.classList.contains('rounded-lg') && el.classList.contains('border')) {
          el.style.display = 'none'
          break
        }
        el = el.parentElement
      }
    }
  }
  hide(document.documentElement)
  const observer = new MutationObserver((records) => {
    records.forEach((record) => {
      if (record.type === 'characterData') {
        const parent = record.target.parentElement
        if (parent) hide(parent)
        return
      }
      record.addedNodes.forEach((node) => {
        if (node.nodeType === Node.ELEMENT_NODE) hide(node as Element)
        else if (node.nodeType === Node.TEXT_NODE && node.parentElement) hide(node.parentElement)
      })
    })
  })
  observer.observe(document.documentElement, { childList: true, characterData: true, subtree: true })
  return () => observer.disconnect()
}


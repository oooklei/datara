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


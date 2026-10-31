import { describe, it, expect } from 'vitest'
import { hideEmbeddedMcpPromoCard, sanitizeEmbeddedBranding } from '../rebuild/embeddedBranding'

/**
 * 契约测试：客户观摩模式下嵌入页不得暴露底层产品名。
 * 固化新 P0「所有页面及嵌入页不得显示底层产品名」的收口规则。
 * REPLACEMENTS 映射以 embeddedBranding.ts 为唯一真源。
 */
describe('embeddedBranding 禁词收口', () => {
  it('替换可见文本中的底层产品名（dolphinscheduler / dbx / 海豚）', () => {
    document.body.innerHTML = '<div>dolphinscheduler 与 dbx 以及海豚调度</div>'
    const dispose = sanitizeEmbeddedBranding(document)
    const text = document.body.textContent ?? ''
    expect(text).toContain('任务运行底座')
    expect(text).toContain('数据开发工具')
    expect(text).not.toContain('dolphinscheduler')
    expect(text).not.toContain('dbx')
    expect(text).not.toContain('海豚')
    dispose()
  })

  it('替换 title / aria-label 属性中的产品名', () => {
    document.body.innerHTML =
      '<button title="dbx 连接" aria-label="dolphinscheduler 状态">x</button>'
    const dispose = sanitizeEmbeddedBranding(document)
    const btn = document.querySelector('button')!
    expect(btn.getAttribute('title')).toBe('数据开发工具 连接')
    expect(btn.getAttribute('aria-label')).toBe('任务运行底座 状态')
    dispose()
  })

  it('空文本与无产品名时不产生副作用', () => {
    document.body.innerHTML = '<span>普通业务文案</span>'
    const dispose = sanitizeEmbeddedBranding(document)
    expect(document.body.textContent).toBe('普通业务文案')
    dispose()
  })
})

describe('嵌入页 MCP 推广卡隐藏', () => {
  function mountWelcomeCard(): HTMLElement {
    document.body.innerHTML = `
      <div class="min-w-0 overflow-hidden rounded-lg border bg-muted/10 px-5 py-4" data-card>
        <div class="flex min-w-0 items-start gap-3">
          <div class="min-w-0 flex-1">
            <div class="text-sm font-medium">AI 编程助手集成</div>
            <p class="mt-1 text-xs leading-5 text-muted-foreground">通过 MCP 使用数据库连接。</p>
            <div class="mt-2 flex flex-wrap items-center gap-2">
              <code class="max-w-full break-all rounded bg-muted px-2 py-0.5 text-[11px] select-all">npx @dbx-app/mcp-server</code>
              <a href="#" class="text-xs text-primary hover:underline">了解更多</a>
            </div>
          </div>
        </div>
      </div>`
    return document.querySelector('[data-card]')!
  }

  it('以 npx 命令为锚点隐藏欢迎页 MCP 推广卡容器', () => {
    const card = mountWelcomeCard()
    const dispose = hideEmbeddedMcpPromoCard(document)
    expect(card.style.display).toBe('none')
    dispose()
  })

  it('后续渲染的同款卡片也会被隐藏', async () => {
    mountWelcomeCard()
    const dispose = hideEmbeddedMcpPromoCard(document)
    const late = document.createElement('div')
    late.className = 'rounded-lg border px-5 py-4'
    late.innerHTML = '<code>npx @dbx-app/mcp-server</code>'
    document.body.appendChild(late)
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(late.style.display).toBe('none')
    dispose()
  })

  it('普通 code 元素不受影响', () => {
    document.body.innerHTML = '<div class="rounded-lg border p-4"><code>select 1</code></div>'
    const box = document.querySelector('div')!
    const dispose = hideEmbeddedMcpPromoCard(document)
    expect(box.style.display).toBe('')
    dispose()
  })
})

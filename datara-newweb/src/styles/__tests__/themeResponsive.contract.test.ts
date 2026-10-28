/**
 * B5-d-2 三档响应式契约：<768 全局降档块必须存在且覆盖关键失控点。
 * §2.3 三档（1440 像素级 / 1024 全功能 / <768 抽屉 + 375 无横向失控）的全局兜底锚。
 * 纯 CSS 兜底属于全局不变量，直读源文件断言，防止后续样式重构时静默丢失。
 * （注：本仓 Vitest 对 `*.css?raw` 返回空串，故用 node:fs 读取。）
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const themeSource = readFileSync(join(import.meta.dirname, '../theme.css'), 'utf-8')

describe('theme.css <768 全局降档契约（B5-d-2）', () => {
  const anchor = '@media (max-width:768px)'
  const idx = themeSource.indexOf(anchor)
  const mq = idx >= 0 ? themeSource.slice(idx) : ''

  it('存在 <768 降档块', () => {
    expect(idx).toBeGreaterThanOrEqual(0)
  })

  it('宽表格兜底：块化 + 横向滚动，排除 Element 内部表', () => {
    expect(mq).toContain('table:not([class*="el-table"]){display:block;overflow-x:auto}')
  })

  it('两栏骨架单列：.split 三变体 + 目录纵排 + 资产/表单网格降档', () => {
    expect(mq).toContain('.split{grid-template-columns:1fr}')
    expect(mq).toContain('.split.even{grid-template-columns:1fr}')
    expect(mq).toContain('.split.filter{grid-template-columns:1fr}')
    expect(mq).toContain('.catalog{flex-direction:column}')
    expect(mq).toContain('.catalog .tree{width:100%')
    expect(mq).toContain('.box-grid{grid-template-columns:1fr}')
    expect(mq).toContain('.form-grid{grid-template-columns:1fr}')
  })

  it('统计网格降档', () => {
    expect(mq).toContain('.stat-grid{grid-template-columns:repeat(2,1fr)}')
    expect(mq).toContain('.stat-row{grid-template-columns:1fr}')
    expect(mq).toContain('.stat-line{grid-template-columns:repeat(2,1fr)}')
  })

  it('桌面档不受影响：降档规则只允许出现在 max-width:768px 媒体查询内', () => {
    const outside = idx >= 0 ? themeSource.slice(0, idx) : themeSource
    expect(outside).not.toContain('.split{grid-template-columns:1fr}')
    expect(outside).not.toContain('.form-grid{grid-template-columns:1fr}')
  })
})

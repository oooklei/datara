/**
 * L3-03 契约测试：项目工作区七段菜单配置（NAV 段名定稿，s251 派令）
 *
 * 锚定面：七段 key 序与 label 沿用 L3-06 已验收 ProjectWorkbenchView 快捷导航
 * （data-nav 锚零破坏，候定稿注记随本票关闭）；key 为 /p/:projectId/<seg> 路由段
 * 与 AppShell data-seg 双消费稳定锚，纪律同 menu.ts 稳定键（非空/唯一/无中文/kebab）。
 */
import { describe, expect, it } from 'vitest'
import { PROJECT_MENU_SECTIONS } from '../projectMenu'

describe('L3-03：projectMenu 七段配置契约（NAV 段名定稿）', () => {
  it('七段序列冻结：key 顺序与 L3-06 已验收段名一致（data-nav 锚零破坏）', () => {
    expect(PROJECT_MENU_SECTIONS.map((s) => s.key)).toEqual([
      'dag',
      'datasource',
      'resources',
      'ide',
      'meta',
      'dep',
      'system',
    ])
  })

  it('label 定稿文案与 L3-06 已验收一致（逐项 toMatchObject）', () => {
    expect([...PROJECT_MENU_SECTIONS]).toMatchObject([
      { key: 'dag', label: '任务中心' },
      { key: 'datasource', label: '数据源' },
      { key: 'resources', label: '资源管理' },
      { key: 'ide', label: 'SQL IDE' },
      { key: 'meta', label: '数据治理' },
      { key: 'dep', label: '部署运维' },
      { key: 'system', label: '系统管理' },
    ])
  })

  it('key 稳定键纪律：非空/唯一/无中文/kebab 命名（路由段 + data-seg 双消费）', () => {
    const keys = PROJECT_MENU_SECTIONS.map((s) => s.key)
    for (const k of keys) {
      expect(k.length).toBeGreaterThan(0)
      expect(k).toMatch(/^[a-z][a-z0-9-]*$/)
    }
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('label 纪律：非空；七段数量恒为 7（L3-06 口径）', () => {
    expect(PROJECT_MENU_SECTIONS).toHaveLength(7)
    for (const s of PROJECT_MENU_SECTIONS) {
      expect(s.label.trim().length).toBeGreaterThan(0)
    }
  })
})

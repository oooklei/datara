import { describe, expect, it } from 'vitest'
import { routes } from '../../router/routes'
import { menuGroups, globalMountedItems } from '../menu'
import { PROJECT_MENU_ITEMS } from '../projectMenu'

const retiredPaths = new Set([
  '/ds/list', '/model/list', '/model/design', '/model/version',
  '/model/lineage', '/model/er', '/meta/lineage', '/meta/map',
  '/meta/catalog', '/open/llm',
])

describe('dbx unified navigation', () => {
  it('does not expose pages delegated to dbx', () => {
    expect(routes.filter((route) => retiredPaths.has(route.path))).toEqual([])
    expect(menuGroups.flatMap((group) => group.items).filter((item) => item.path && retiredPaths.has(item.path))).toEqual([])
    expect(PROJECT_MENU_ITEMS.filter((item) => retiredPaths.has(item.path))).toEqual([])
    expect(globalMountedItems).toEqual([])
  })

  it('keeps the integrated dbx SQL IDE host entry', () => {
    expect(routes.some((route) => route.path === '/ide')).toBe(true)
    expect(menuGroups.flatMap((group) => group.items).some((item) => item.path === '/ide')).toBe(true)
    expect(PROJECT_MENU_ITEMS.some((item) => item.path === '/ide')).toBe(true)
  })

  it('keeps all ten governance entries', () => {
    const governance = menuGroups.find((group) => group.id === 'governance')
    expect(governance?.items.map((item) => item.id)).toEqual([
      'meta-tag', 'std-element', 'ind-list', 'ind-board', 'ind-consistency',
      'qc-rule', 'qc-task', 'qc-exception', 'qc-report', 'qc-alarm',
    ])
  })
})

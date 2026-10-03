// @vitest-environment happy-dom
/**
 * Palette 工作流目录外部变更刷新（GraphWorkbench 新建工作流联动）：
 * - 挂载时拉取定义池 + 分类目录；
 * - bus 'wf-definitions-changed' 广播 → 立即重拉（新建工作流后无需重挂载画布即可见）；
 * - 组件卸载解绑订阅（不泄漏 handler）。
 * services 模块 mock；bus 用真实单例（生产同源）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listDefinitionsSpy = vi.hoisted(() => vi.fn())
const listCategoriesSpy = vi.hoisted(() => vi.fn())
vi.mock('../../../services', () => ({
  isMock: false,
  listDefinitions: listDefinitionsSpy,
  listCategories: listCategoriesSpy,
  deleteDefinition: vi.fn(),
  createCategory: vi.fn(),
  setWfTags: vi.fn(),
  /* Palette 类型徽标/分组映射依赖的标签常量（对齐 graphApi.ts 实际值） */
  SYNC_TAG: '同步',
  ETL_TAG: 'ETL',
  STREAM_TAG: '流',
}))

import { bus } from '../../../services/eventBus'
import Palette from '../Palette.vue'
import { dagProfile } from '../../profiles'

function mountPalette() {
  return mount(Palette, { props: { profile: dagProfile, defaultTab: 'wf' as const } })
}

beforeEach(() => {
  vi.clearAllMocks()
  listDefinitionsSpy.mockResolvedValue([
    { id: 'wf_a', name: '已有流', code: 1, tags: [] },
  ])
  listCategoriesSpy.mockResolvedValue([
    { id: 'builtin:同步', name: '同步', builtin: true },
    { id: 'custom:9', name: '营销域', builtin: false },
  ])
})

describe('Palette 订阅 wf-definitions-changed', () => {
  it('挂载即拉取定义池与分类', async () => {
    const w = mountPalette()
    await flushPromises()
    expect(listDefinitionsSpy).toHaveBeenCalledTimes(1)
    expect(listCategoriesSpy).toHaveBeenCalledTimes(1)
    w.unmount() // bus 是文件级真单例：及时卸载防 handler 跨用例泄漏污染计数
  })

  it('总线广播 → 立即重拉定义池（新建工作流即时可见）', async () => {
    const w = mountPalette()
    await flushPromises()
    expect(w.text()).not.toContain('新建流') // 首次挂载仅旧池
    listDefinitionsSpy.mockResolvedValue([
      { id: 'wf_a', name: '已有流', code: 1, tags: [] },
      { id: 'wf_new9', name: '新建流', code: 21, tags: ['ETL'] },
    ])
    bus.emit('wf-definitions-changed', { id: 'wf_new9' })
    await flushPromises()
    expect(listDefinitionsSpy).toHaveBeenCalledTimes(2)
    expect(w.text()).toContain('新建流')
    w.unmount()
  })

  it('卸载后解绑订阅：广播不再触发重拉（无 handler 泄漏）', async () => {
    const w = mountPalette()
    await flushPromises()
    w.unmount()
    bus.emit('wf-definitions-changed', { id: 'wf_x' })
    await flushPromises()
    expect(listDefinitionsSpy).toHaveBeenCalledTimes(1)
  })
})

// @vitest-environment happy-dom
/**
 * 组件治理三页整合宿主（ComponentHubView）用例：
 * - 页签默认 catalog；query.tab 深链分派（designer 页签吃 query.designType）
 * - 切页签 router.replace 单向同步（designer 深链带 designType，其余页签不带）
 * - props 回调互联：目录/基线化 openDesigner → 切设计器并带 type；
 *   设计器 goCatalog → 切目录；designTypeChange → designType 与深链同步
 * - v-show 保活：三视图同挂载，页签切换不销毁（设计器编辑态跨页签保留）
 * 三个子视图以桩替换（props/emits 对齐），vue-router 模块 mock。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const routeState = vi.hoisted(() => ({ query: {} as Record<string, unknown> }))
/* router.replace 返回 Promise（真实契约），宿主 .catch 链依赖之 */
const replaceSpy = vi.hoisted(() => vi.fn(() => Promise.resolve()))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeState.query }),
  useRouter: () => ({ replace: replaceSpy }),
}))

vi.mock('../ComponentCatalogView.vue', () => ({
  default: {
    name: 'CatalogStub',
    props: ['openDesigner'],
    template: `<section class="stub-catalog">
      <button class="c-open-new" @click="openDesigner && openDesigner()" />
      <button class="c-open-t" @click="openDesigner && openDesigner('op_filter')" />
    </section>`,
  },
}))
vi.mock('../BaselineWorkbenchView.vue', () => ({
  default: {
    name: 'BaselineStub',
    props: ['openDesigner'],
    template: '<section class="stub-baseline"><button class="b-open" @click="openDesigner && openDesigner(\'op_filter\')" /></section>',
  },
}))
vi.mock('../pageDesigner/PageDesignerView.vue', () => ({
  default: {
    name: 'DesignerStub',
    props: ['designType', 'goCatalog'],
    emits: ['designTypeChange'],
    template: `<section class="stub-designer">
      <span class="d-type">{{ designType }}</span>
      <button class="d-back" @click="goCatalog && goCatalog()" />
      <button class="d-created" @click="$emit('designTypeChange', 'page_new')" />
    </section>`,
  },
}))

import ComponentHubView from '../ComponentHubView.vue'

function mountHub() {
  return mount(ComponentHubView)
}
const activeTab = (w: ReturnType<typeof mountHub>) => w.find('.hub-tab.on').text()
const shown = (w: ReturnType<typeof mountHub>, sel: string) => {
  const el = w.find(sel)
  return el.exists() && !(el.element as HTMLElement).style.display.includes('none')
}

beforeEach(() => {
  vi.clearAllMocks()
  routeState.query = {}
})

describe('ComponentHubView 三页整合宿主', () => {
  it('默认页签=组件目录；三视图同挂载（v-show 保活）', () => {
    const w = mountHub()
    expect(activeTab(w)).toBe('组件目录')
    expect(w.find('.stub-catalog').exists()).toBe(true)
    expect(w.find('.stub-baseline').exists()).toBe(true)
    expect(w.find('.stub-designer').exists()).toBe(true)
  })

  it('深链分派：?tab=designer&designType=page_demo → 设计器页签且 type 透传', () => {
    routeState.query = { tab: 'designer', designType: 'page_demo' }
    const w = mountHub()
    expect(activeTab(w)).toBe('组件设计器')
    expect(shown(w, '.stub-designer')).toBe(true)
    expect(w.find('.d-type').text()).toBe('page_demo')
  })

  it('深链分派：?tab=baseline → 基线化页签；非法 tab 兜底目录', () => {
    routeState.query = { tab: 'baseline' }
    const w = mountHub()
    expect(activeTab(w)).toBe('基线化工作台')
    routeState.query = { tab: 'whatever' }
    const w2 = mountHub()
    expect(activeTab(w2)).toBe('组件目录')
  })

  it('切页签：router.replace 单向同步（designer 无 type 不带 designType）', async () => {
    const w = mountHub()
    await w.findAll('.hub-tab').find((b) => b.text() === '基线化工作台')!.trigger('click')
    expect(replaceSpy).toHaveBeenLastCalledWith({ query: { tab: 'baseline' } })
    await w.findAll('.hub-tab').find((b) => b.text() === '组件设计器')!.trigger('click')
    expect(replaceSpy).toHaveBeenLastCalledWith({ query: { tab: 'designer' } })
    expect(w.find('.d-type').text()).toBe('')
  })

  it('目录 openDesigner：带 type 切设计器并同步深链；缺省 = 新建态', async () => {
    const w = mountHub()
    await w.find('.c-open-t').trigger('click')
    expect(activeTab(w)).toBe('组件设计器')
    expect(w.find('.d-type').text()).toBe('op_filter')
    expect(replaceSpy).toHaveBeenLastCalledWith({ query: { tab: 'designer', designType: 'op_filter' } })
    await w.find('.c-open-new').trigger('click')
    expect(w.find('.d-type').text()).toBe('')
    expect(replaceSpy).toHaveBeenLastCalledWith({ query: { tab: 'designer' } })
  })

  it('基线化 openDesigner：同样切设计器并带 type', async () => {
    const w = mountHub()
    await w.find('.b-open').trigger('click')
    expect(activeTab(w)).toBe('组件设计器')
    expect(w.find('.d-type').text()).toBe('op_filter')
  })

  it('设计器 goCatalog：切回目录并清深链；designTypeChange：type 与深链同步', async () => {
    routeState.query = { tab: 'designer', designType: 'page_demo' }
    const w = mountHub()
    await w.find('.d-back').trigger('click')
    expect(activeTab(w)).toBe('组件目录')
    expect(replaceSpy).toHaveBeenLastCalledWith({ query: { tab: 'catalog' } })
    await w.find('.d-created').trigger('click')
    expect(w.find('.d-type').text()).toBe('page_new')
    expect(replaceSpy).toHaveBeenLastCalledWith({ query: { tab: 'designer', designType: 'page_new' } })
  })
})

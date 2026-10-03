// @vitest-environment happy-dom
/**
 * 新建工作流对话框挂载用例（GraphWorkbench 页面功能扩展）：
 * - 打开时重置表单并拉取分类目录（根目录 + 内置三组 + 自定义目录）；
 * - 空白名称提交被拦截（不发起创建请求）；
 * - real 提交载荷：名称裁剪 + tags=[分类] + remark，created 事件携带 id/name/type/code；
 * - 内置分类映射画布类型（同步→sync、ETL→etl、流→stream），根目录→wf。
 * services / seed 以模块 mock 注入；el-* 组件桩掉消噪音（与基线化工作台用例同法）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const createDefinitionSpy = vi.hoisted(() => vi.fn())
const listCategoriesSpy = vi.hoisted(() => vi.fn())
vi.mock('../../../services', () => ({
  isMock: false,
  graphService: { save: vi.fn() },
  createDefinition: createDefinitionSpy,
  listCategories: listCategoriesSpy,
}))
vi.mock('../../../services/mock/seed', () => ({
  newWorkflowDoc: vi.fn(() => ({ id: 'wf_mock', name: 'x', version: 1, meta: { profile: 'dag' }, nodes: [], edges: [] })),
}))

import WfCreateDialog from '../WfCreateDialog.vue'

const stubs = {
  ElDialog: {
    props: ['modelValue', 'title'],
    emits: ['update:modelValue'],
    template: '<div v-if="modelValue" class="dlg-stub"><slot /><slot name="footer" /></div>',
  },
  ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' },
}

function mountDialog() {
  return mount(WfCreateDialog, { props: { modelValue: false }, global: { components: stubs } })
}

async function open(w: ReturnType<typeof mountDialog>) {
  await w.setProps({ modelValue: true })
  await flushPromises()
}

function setName(w: ReturnType<typeof mountDialog>, v: string) {
  return w.find('input[placeholder*="工作流名称"]').setValue(v)
}

beforeEach(() => {
  vi.clearAllMocks()
  listCategoriesSpy.mockResolvedValue([
    { id: 'builtin:同步', name: '同步', builtin: true },
    { id: 'builtin:ETL', name: 'ETL', builtin: true },
    { id: 'builtin:流', name: '流', builtin: true },
    { id: 'custom:2', name: '营销域', builtin: false },
  ])
  createDefinitionSpy.mockResolvedValue({ id: 'wf_new9', code: 21, version: 1 })
})

describe('WfCreateDialog 新建工作流对话框', () => {
  it('打开时重置表单并拉取分类：根目录 + 4 个目录选项', async () => {
    const w = mountDialog()
    await open(w)
    expect(listCategoriesSpy).toHaveBeenCalledTimes(1)
    const options = w.findAll('select option')
    expect(options).toHaveLength(5) // 根目录 + 同步/ETL/流/营销域
    expect(options[0].text()).toContain('根目录')
    expect(options[4].text()).toContain('营销域（自定义）')
  })

  it('空白名称提交被拦截：不发创建请求、不 emit created', async () => {
    const w = mountDialog()
    await open(w)
    await setName(w, '   ')
    await w.find('input[placeholder*="工作流名称"]').trigger('keydown.enter')
    await flushPromises()
    expect(createDefinitionSpy).not.toHaveBeenCalled()
    expect(w.emitted('created')).toBeUndefined()
  })

  it('real 提交：载荷 name/tags/remark 齐全，created 事件携带 id/name/type/code 且对话框关闭', async () => {
    const w = mountDialog()
    await open(w)
    await setName(w, '  订单加工流  ')
    await w.find('select').setValue('ETL')
    await w.find('textarea').setValue('季度扩容新增')
    await w.findAll('.dlg-stub button').find((b) => b.text().includes('创建并编排'))!.trigger('click')
    await flushPromises()
    expect(createDefinitionSpy).toHaveBeenCalledWith('订单加工流', { tags: ['ETL'], remark: '季度扩容新增' })
    const created = w.emitted('created')![0][0] as Record<string, unknown>
    expect(created).toEqual({ id: 'wf_new9', name: '订单加工流', type: 'etl', code: 21 })
    expect(w.emitted('update:modelValue')!.at(-1)![0]).toBe(false) // 成功后关对话框
  })

  it('根目录（不选分类）→ tags 空 → created type=wf', async () => {
    const w = mountDialog()
    await open(w)
    await setName(w, '普通流')
    await w.findAll('.dlg-stub button').find((b) => b.text().includes('创建并编排'))!.trigger('click')
    await flushPromises()
    expect(createDefinitionSpy).toHaveBeenCalledWith('普通流', { tags: [], remark: '' })
    const created = w.emitted('created')![0][0] as Record<string, unknown>
    expect(created.type).toBe('wf')
  })

  it('创建接口失败：错误不 emit created，对话框保持打开', async () => {
    createDefinitionSpy.mockRejectedValueOnce(new Error('后端不可达'))
    const w = mountDialog()
    await open(w)
    await setName(w, '失败流')
    await w.findAll('.dlg-stub button').find((b) => b.text().includes('创建并编排'))!.trigger('click')
    await flushPromises()
    expect(w.emitted('created')).toBeUndefined()
    expect(w.emitted('update:modelValue')).toBeUndefined()
  })
})

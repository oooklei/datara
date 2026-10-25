// @vitest-environment happy-dom
// VariablesManageDialog 组件测试（L5-02；蓝本=SyncFormValidationView.test.ts：vi.hoisted 契约 mock + mount ElementPlus + data-testid）。
// 覆盖票面退出标准：global/project 两域承载 + 敏感打码 + upsert 保存链 + 不可保存域前置拒存（七级不收窄）+ 只读拒改。
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

const api = vi.hoisted(() => ({
  listVariables: vi.fn(),
  saveVariable: vi.fn(),
}))

const authState = vi.hoisted(() => ({ canEdit: true }))

vi.mock('../../services/rebuild/variableApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/rebuild/variableApi')>()
  return { ...actual, createVariableContract: () => api }
})

vi.mock('../../stores/auth', () => ({ useAuthStore: () => authState }))

import VariablesManageDialog from './VariablesManageDialog.vue'

afterEach(() => vi.clearAllMocks())

/** ElSelect 在 happy-dom 下递归更新爆栈（Maximum recursive updates exceeded）——库内先例（PageInspector.test.ts）一律 stub：
 * 保留 name/props/emits 以便 findComponent + $emit('update:modelValue') 模拟选中 */
const ElSelectStub = {
  name: 'ElSelect',
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: '<div class="stub-select"><slot /></div>',
}

/** 挂载并以 false→true 过渡打开对话框（loadRows 挂在 watch 上，需真实开启转移触发） */
async function openDialog() {
  const wrapper = mount(VariablesManageDialog, {
    props: { modelValue: false },
    global: { plugins: [ElementPlus], stubs: { teleport: true, ElSelect: ElSelectStub, ElOption: true } },
  })
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  await nextTick()
  return wrapper
}

describe('VariablesManageDialog', () => {
  it('loads global/project rows on open and masks sensitive values', async () => {
    api.listVariables.mockResolvedValue([
      { scope: 'project', name: 'region', valueType: 'string', value: 'cn', sensitive: false, description: '区域' },
      { scope: 'global', name: 'api_key', valueType: 'string', value: 'sk-secret-123', sensitive: true, description: '' },
    ])
    const wrapper = await openDialog()

    expect(api.listVariables).toHaveBeenCalledWith(1, ['global', 'project'])
    const table = wrapper.get('[data-testid="variables-table"]')
    expect(table.text()).toContain('region')
    expect(table.text()).toContain('●●●●●●')
    expect(table.text()).not.toContain('sk-secret-123')
    wrapper.unmount()
  })

  it('saves via upsert and reloads the list (global scope, persistable)', async () => {
    api.listVariables.mockResolvedValue([])
    api.saveVariable.mockResolvedValue({ saved: true, scope: 'global', name: 'region' })
    const wrapper = await openDialog()

    await wrapper.get('[data-testid="variables-name"]').setValue('region')
    await wrapper.get('[data-testid="variables-save"]').trigger('click')
    await flushPromises()

    expect(api.saveVariable).toHaveBeenCalledTimes(1)
    expect(api.saveVariable).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ scope: 'global', name: 'region', valueType: 'string' }),
    )
    // 保存成功后 resetForm + loadRows 复载（初始 1 次 + 保存后 1 次）
    expect(api.listVariables).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('keeps all seven scopes selectable and blocks save for non-persistable scope (run) with hint', async () => {
    api.listVariables.mockResolvedValue([])
    const wrapper = await openDialog()

    // 作用域选择器=表单内首个 el-select；发出 update:modelValue 模拟选中 run（不收窄：可选中）
    const scopeSelect = wrapper.findComponent({ name: 'ElSelect' })
    expect(scopeSelect.exists()).toBe(true)
    scopeSelect.vm.$emit('update:modelValue', 'run')
    await nextTick()

    const hint = wrapper.get('[data-testid="variables-scope-hint"]')
    expect(hint.text()).toContain('运行时作用域不可持久化存储')

    await wrapper.get('[data-testid="variables-name"]').setValue('x')
    await wrapper.get('[data-testid="variables-save"]').trigger('click')
    await flushPromises()

    expect(api.saveVariable).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('rejects saving when role is read-only (canEdit=false)', async () => {
    authState.canEdit = false
    api.listVariables.mockResolvedValue([])
    const wrapper = await openDialog()

    await wrapper.get('[data-testid="variables-name"]').setValue('region')
    await wrapper.get('[data-testid="variables-save"]').trigger('click')
    await flushPromises()

    expect(api.saveVariable).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

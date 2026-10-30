import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { completionStatus, currentCompletions, startCompletion } from '@codemirror/autocomplete'
import type { EditorView } from '@codemirror/view'
import CodeEditor from '../CodeEditor.vue'

/** S1 能力面契约：变量补全 / 关系名补全 / 表字段补全 / 三态分色 / lint 防抖 / 失败吞掉。 */

function viewOf(wrapper: ReturnType<typeof mount>): EditorView {
  const view = (wrapper.vm as unknown as { getView: () => EditorView | undefined }).getView()
  if (!view) throw new Error('CodeMirror 视图未挂载')
  return view
}

async function labelsAfter(view: EditorView, text: string): Promise<string[]> {
  view.dispatch({ changes: { from: 0, insert: text }, selection: { anchor: text.length } })
  startCompletion(view)
  await vi.waitFor(() => expect(completionStatus(view.state)).toBe('active'))
  return currentCompletions(view.state).map((option) => option.label)
}

describe('CodeEditor S1 能力面', () => {
  it('按 variables 补全 ${scope.name} 变量引用', async () => {
    const wrapper = mount(CodeEditor, {
      props: {
        modelValue: '',
        language: 'sql',
        variables: [
          { scope: 'global', name: 'region' },
          { scope: 'project', name: 'biz_date' },
        ],
      },
    })
    const labels = await labelsAfter(viewOf(wrapper), 'SELECT ${g')
    expect(labels).toContain('${global.region}')
    expect(labels).not.toContain('${project.biz_date}')
    wrapper.unmount()
  })

  it('按 relationNames 补全表/视图名', async () => {
    const wrapper = mount(CodeEditor, {
      props: { modelValue: '', language: 'sql', relationNames: ['orders', 'customers'] },
    })
    const labels = await labelsAfter(viewOf(wrapper), 'SELECT cu')
    expect(labels).toContain('customers')
    expect(labels).not.toContain('orders')
    wrapper.unmount()
  })

  it('按 tableColumns 在 `table.` 后补全字段', async () => {
    const wrapper = mount(CodeEditor, {
      props: {
        modelValue: '',
        language: 'sql',
        tableColumns: {
          orders: [{ name: 'order_id' }, { name: 'amount' }],
          customers: [{ name: 'customer_id' }],
        },
      },
    })
    const labels = await labelsAfter(viewOf(wrapper), 'SELECT orders.')
    expect(labels).toContain('order_id')
    expect(labels).toContain('amount')
    expect(labels).not.toContain('customer_id')
    wrapper.unmount()
  })

  it('columnsProvider 懒加载未预载表的字段', async () => {
    const columnsProvider = vi.fn().mockResolvedValue([{ name: 'order_id', dataType: 'int' }])
    const wrapper = mount(CodeEditor, {
      props: { modelValue: '', language: 'sql', columnsProvider },
    })
    const labels = await labelsAfter(viewOf(wrapper), 'SELECT orders.')
    expect(columnsProvider).toHaveBeenCalledWith('orders')
    expect(labels).toContain('order_id')
    wrapper.unmount()
  })

  it('变量引用三态分色：已定义 / 未定义 / 语法异常', async () => {
    const wrapper = mount(CodeEditor, {
      props: {
        modelValue: 'SELECT ${global.region}, ${global.missing}, ${oops}',
        language: 'sql',
        variables: [{ scope: 'global', name: 'region' }],
      },
    })
    const host = wrapper.find('.code-editor')
    await flushPromises()
    expect(host.findAll('.cm-var-token:not(.cm-var-undefined)')).toHaveLength(1)
    expect(host.findAll('.cm-var-undefined')).toHaveLength(1)
    expect(host.findAll('.cm-var-syntax-error')).toHaveLength(1)

    await wrapper.setProps({ modelValue: 'SELECT ${env.cluster}' })
    await flushPromises()
    expect(host.findAll('.cm-var-undefined')).toHaveLength(1)
    expect(host.findAll('.cm-var-syntax-error')).toHaveLength(0)
    wrapper.unmount()
  })

  it('variables 缺省时全部按已定义处理', async () => {
    const wrapper = mount(CodeEditor, { props: { modelValue: 'SELECT ${global.anything}', language: 'sql' } })
    const host = wrapper.find('.code-editor')
    await flushPromises()
    expect(host.findAll('.cm-var-token')).toHaveLength(1)
    expect(host.findAll('.cm-var-undefined')).toHaveLength(0)
    wrapper.unmount()
  })

  it('lint 防抖调用 lintProvider 并渲染诊断', async () => {
    const lintProvider = vi.fn().mockResolvedValue([{ line: 1, col: 1, severity: 'error', message: '语法错误：缺少分号' }])
    const wrapper = mount(CodeEditor, { props: { modelValue: 'select 1', language: 'sql', lintProvider } })
    const host = wrapper.find('.code-editor')
    await vi.waitFor(
      () => {
        expect(lintProvider).toHaveBeenCalledWith('select 1')
        expect(host.findAll('.cm-lintRange-error').length).toBeGreaterThan(0)
      },
      { timeout: 3000 },
    )
    wrapper.unmount()
  })

  it('lintProvider 失败时静默吞掉', async () => {
    const lintProvider = vi.fn().mockRejectedValue(new Error('backend down'))
    const wrapper = mount(CodeEditor, { props: { modelValue: 'select 1', language: 'sql', lintProvider } })
    await vi.waitFor(() => expect(lintProvider).toHaveBeenCalled(), { timeout: 3000 })
    await flushPromises()
    expect(wrapper.find('.code-editor').findAll('.cm-lintRange-error')).toHaveLength(0)
    wrapper.unmount()
  })
})

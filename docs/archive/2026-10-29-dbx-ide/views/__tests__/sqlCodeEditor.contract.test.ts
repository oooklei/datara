import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { completionStatus, currentCompletions, startCompletion } from '@codemirror/autocomplete'
import type { EditorView } from '@codemirror/view'
import Editor from '../ide/SqlCodeEditor.vue'

/** B4-b S1/S7：SqlCodeEditor 能力面契约（补全/分色/未定义警告/lint 防抖）。 */
describe('SqlCodeEditor 能力面（S1/S7）', () => {
  it('completes ${scope.name} variable references from the variables prop (S7)', async () => {
    const w = mount(Editor, {
      props: {
        modelValue: '',
        variables: [
          { scope: 'global', name: 'region' },
          { scope: 'project', name: 'biz_date' },
        ],
      },
    })
    const view = (w.vm as unknown as { getView: () => EditorView | undefined }).getView()
    expect(view).toBeDefined()
    view!.dispatch({
      changes: { from: 0, insert: 'SELECT ${g' },
      selection: { anchor: 'SELECT ${g'.length },
    })
    startCompletion(view!)
    await vi.waitFor(() => expect(completionStatus(view!.state)).toBe('active'))
    const labels = currentCompletions(view!.state).map((option) => option.label)
    expect(labels).toContain('${global.region}')
    expect(labels).not.toContain('${project.biz_date}')
    w.unmount()
  })

  it('completes relation names from the relationNames prop (S1)', async () => {
    const w = mount(Editor, {
      props: { modelValue: '', relationNames: ['orders', 'customers'] },
    })
    const view = (w.vm as unknown as { getView: () => EditorView | undefined }).getView()!
    view.dispatch({
      changes: { from: 0, insert: 'SELECT cu' },
      selection: { anchor: 'SELECT cu'.length },
    })
    startCompletion(view)
    await vi.waitFor(() => expect(completionStatus(view.state)).toBe('active'))
    const labels = currentCompletions(view.state).map((option) => option.label)
    expect(labels).toContain('customers')
    expect(labels).not.toContain('orders')
    w.unmount()
  })

  it('completes table fields after a `table.` qualifier from the tableColumns prop (S1)', async () => {
    const w = mount(Editor, {
      props: {
        modelValue: '',
        tableColumns: {
          orders: [{ name: 'order_id' }, { name: 'amount' }],
          customers: [{ name: 'customer_id' }],
        },
      },
    })
    const view = (w.vm as unknown as { getView: () => EditorView | undefined }).getView()!
    view.dispatch({
      changes: { from: 0, insert: 'SELECT orders.' },
      selection: { anchor: 'SELECT orders.'.length },
    })
    startCompletion(view)
    await vi.waitFor(() => expect(completionStatus(view.state)).toBe('active'))
    const labels = currentCompletions(view.state).map((option) => option.label)
    expect(labels).toContain('order_id')
    expect(labels).toContain('amount')
    expect(labels).not.toContain('customer_id')
    w.unmount()
  })

  it('colors defined/undefined variable refs and flags syntax errors (S7)', async () => {
    const w = mount(Editor, {
      props: {
        modelValue: 'SELECT ${global.region}, ${global.missing}, ${oops}',
        variables: [{ scope: 'global', name: 'region' }],
      },
    })
    const host = w.find('[data-codemirror-editor]')
    await flushPromises()
    expect(host.findAll('.cm-var-token:not(.cm-var-undefined)')).toHaveLength(1)
    expect(host.findAll('.cm-var-undefined')).toHaveLength(1)
    expect(host.findAll('.cm-var-syntax-error')).toHaveLength(1)

    // 文档变更后重算：未定义引用仍降级着色
    await w.setProps({ modelValue: 'SELECT ${env.cluster}' })
    await flushPromises()
    expect(host.findAll('.cm-var-undefined')).toHaveLength(1)
    expect(host.findAll('.cm-var-syntax-error')).toHaveLength(0)
    w.unmount()
  })

  it('treats every ref as defined when the variables prop is absent (standalone usage)', async () => {
    const w = mount(Editor, { props: { modelValue: 'SELECT ${global.anything}' } })
    const host = w.find('[data-codemirror-editor]')
    await flushPromises()
    expect(host.findAll('.cm-var-token')).toHaveLength(1)
    expect(host.findAll('.cm-var-undefined')).toHaveLength(0)
    w.unmount()
  })

  it('runs the debounced lint provider and renders editor diagnostics (S1)', async () => {
    const lintProvider = vi.fn().mockResolvedValue([{ line: 1, col: 1, severity: 'error', message: '语法错误：缺少分号' }])
    const w = mount(Editor, { props: { modelValue: 'select 1', lintProvider } })
    const host = w.find('[data-codemirror-editor]')
    await vi.waitFor(
      () => {
        expect(lintProvider).toHaveBeenCalledWith('select 1')
        expect(host.findAll('.cm-lintRange-error').length).toBeGreaterThan(0)
      },
      { timeout: 3000 },
    )
    w.unmount()
  })

  it('swallows lint provider failures instead of throwing into the editor (S1)', async () => {
    const lintProvider = vi.fn().mockRejectedValue(new Error('backend down'))
    const w = mount(Editor, { props: { modelValue: 'select 1', lintProvider } })
    await vi.waitFor(() => expect(lintProvider).toHaveBeenCalled(), { timeout: 3000 })
    await flushPromises()
    expect(w.find('[data-codemirror-editor]').findAll('.cm-lintRange-error')).toHaveLength(0)
    w.unmount()
  })
})

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { uploadResource, listResources, listResourceVersions, bindResourceVersion } = vi.hoisted(() => ({
  uploadResource: vi.fn(),
  listResources: vi.fn(),
  listResourceVersions: vi.fn(),
  bindResourceVersion: vi.fn(),
}))

vi.mock('../../services/rebuild/resourceApi', async (original) => {
  const actual = await original<typeof import('../../services/rebuild/resourceApi')>()
  return {
    ...actual,
    createResourceContract: () => ({
      uploadResource,
      listResources,
      listResourceVersions,
      bindResourceVersion,
      getResourceVersion: vi.fn(),
    }),
  }
})

import ScriptResourceEditor from '../ScriptResourceEditor.vue'

const variableInputStub = {
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: '<textarea data-inline-source :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
}

describe('script resource editor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listResources.mockResolvedValue([{ resourceId: 8, name: 'job.sh', kind: 'shell', sizeBytes: 12, latestVersion: 3 }])
    listResourceVersions.mockResolvedValue([
      { resourceId: 8, version: 2, sizeBytes: 10, digest: 'sha-2', uploadedAt: '2026-10-25T00:00:00Z' },
      { resourceId: 8, version: 3, sizeBytes: 12, digest: 'sha-3', uploadedAt: '2026-10-25T01:00:00Z' },
    ])
    bindResourceVersion.mockResolvedValue({ bound: true, bindingId: 19 })
  })

  it('Shell 内联代码统一写入 script 参数且不再产生 command', async () => {
    const wrapper = mount(ScriptResourceEditor, {
      props: { projectId: 7, workflowId: 11, workflowVersion: 1, taskId: 'shell_1', kind: 'shell', modelValue: {} },
      global: { stubs: { VariableReferenceInput: variableInputStub } },
    })
    await wrapper.find('[data-inline-source]').setValue('echo ready')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({ sourceMode: 'inline', script: 'echo ready' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).not.toHaveProperty('command')
  })

  it('只在用户选择明确版本后调用绑定 API 并写入 resourceRef', async () => {
    const wrapper = mount(ScriptResourceEditor, {
      props: {
        projectId: 7,
        workflowId: 11,
        workflowVersion: 1,
        taskId: 'shell_1',
        kind: 'shell',
        modelValue: { sourceMode: 'resource' },
      },
      global: { stubs: { VariableReferenceInput: variableInputStub } },
    })
    await flushPromises()
    expect(listResources).toHaveBeenCalledWith(7, 'shell')
    await wrapper.find('[data-resource-select]').setValue('8')
    await flushPromises()
    expect(listResourceVersions).toHaveBeenCalledWith(8, 7)
    expect(bindResourceVersion).not.toHaveBeenCalled()
    await wrapper.find('[data-version-select]').setValue('2')
    await wrapper.find('[data-bind-resource]').trigger('click')
    await flushPromises()
    expect(bindResourceVersion).toHaveBeenCalledWith({
      projectId: 7,
      workflowId: 11,
      workflowVersion: 1,
      taskId: 'shell_1',
      resourceId: 8,
      resourceVersion: 2,
    })
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      sourceMode: 'resource',
      resourceRef: { resourceId: 8, version: 2 },
    })
  })

  it('上传成功后选中服务端返回的不可变版本但仍等待用户确认绑定', async () => {
    uploadResource.mockResolvedValue({ resourceId: 9, version: 4, sizeBytes: 11, digest: 'sha-4', uploadedAt: '2026-10-25T02:00:00Z' })
    listResources.mockResolvedValue([{ resourceId: 9, name: 'task.py', kind: 'python', sizeBytes: 11, latestVersion: 4 }])
    listResourceVersions.mockResolvedValue([{ resourceId: 9, version: 4, sizeBytes: 11, digest: 'sha-4', uploadedAt: '2026-10-25T02:00:00Z' }])
    const wrapper = mount(ScriptResourceEditor, {
      props: { projectId: 7, workflowId: 11, workflowVersion: 1, taskId: 'python_1', kind: 'python', modelValue: { sourceMode: 'resource' } },
      global: { stubs: { VariableReferenceInput: variableInputStub } },
    })
    await flushPromises()
    const file = new File(['print(1)'], 'task.py', { type: 'text/x-python' })
    Object.defineProperty(file, 'arrayBuffer', { value: async () => new TextEncoder().encode('print(1)').buffer })
    const input = wrapper.find<HTMLInputElement>('[data-resource-upload]')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
    expect(uploadResource).toHaveBeenCalledWith(expect.objectContaining({ projectId: 7, kind: 'python', filename: 'task.py' }))
    expect((wrapper.find('[data-resource-select]').element as HTMLSelectElement).value).toBe('9')
    expect((wrapper.find('[data-version-select]').element as HTMLSelectElement).value).toBe('4')
    expect(bindResourceVersion).not.toHaveBeenCalled()
  })
})

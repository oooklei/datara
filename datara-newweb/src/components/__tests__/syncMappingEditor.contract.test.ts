import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { explore, autoMap, savePlan } = vi.hoisted(() => ({ explore: vi.fn(), autoMap: vi.fn(), savePlan: vi.fn() }))
vi.mock('../../services/rebuild/syncComponentApi', async (original) => {
  const actual = await original<typeof import('../../services/rebuild/syncComponentApi')>()
  return { ...actual, createSyncComponentContract: () => ({ getCapabilities: vi.fn(), explore, autoMap, savePlan, listPlans: vi.fn() }) }
})
import SyncMappingEditor from '../SyncMappingEditor.vue'

const variableInputStub = {
  props: ['modelValue', 'context', 'label'],
  emits: ['update:modelValue'],
  template: '<button data-variable-input :data-label="label" @click="$emit(\'update:modelValue\', \'${workflow.dynamic_value}\')">{{ label }}</button>',
}

describe('sync mapping editor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    explore.mockResolvedValue({ items: [{ column_name: 'id', data_type: 'int' }], truncated: false, limit: 200 })
    autoMap.mockResolvedValue([{ source_column: 'id', target_column: 'id', source_type: 'int', target_type: 'int', transform_expression: '', nullable: true, default_value: null, mapping_status: 'AUTO' }])
    savePlan.mockResolvedValue({ saved: true, workflow_version: 1, task_id: 'sync_1' })
  })

  it('探查生成映射，允许调整并保存真实计划', async () => {
    const wrapper = mount(SyncMappingEditor, { props: { projectId: 7, workflowId: 11, workflowVersion: 1, taskId: 'sync_1', modelValue: { source: { datasource_id: 1, schema: 'ods', object: 'src' }, target: { datasource_id: 2, schema: 'dw', object: 'dst' } } } })
    await wrapper.get('[data-test="sync-explore"]').trigger('click')
    await flushPromises()
    expect(explore).toHaveBeenCalledTimes(2)
    expect(autoMap).toHaveBeenCalledWith(7, expect.objectContaining({ object: 'src' }), expect.objectContaining({ object: 'dst' }))
    expect(wrapper.find('table').exists()).toBe(true)
    await wrapper.find('table input').setValue('id_adjusted')
    await wrapper.get('[data-test="sync-save"]').trigger('click')
    await flushPromises()
    expect(savePlan).toHaveBeenCalledWith(expect.objectContaining({ project_id: 7, workflow_id: 11, task_id: 'sync_1', mappings: [expect.objectContaining({ source_column: 'id_adjusted' })] }))
  })

  it('将探查表单投影为 endpoint_select 可执行参数且保留 baseMode', async () => {
    const wrapper = mount(SyncMappingEditor, {
      props: {
        projectId: 7,
        workflowId: 11,
        workflowVersion: 1,
        taskId: 'endpoint_1',
        modelValue: {
          baseMode: 'src_base',
          source: { datasource_id: 1, schema: 'ods', object: 'src' },
          target: { datasource_id: 2, schema: 'dw', object: 'dst' },
        },
      },
    })

    await wrapper.get('[data-test="sync-explore"]').trigger('click')
    await flushPromises()

    const updates = wrapper.emitted('update:modelValue') as Array<[Record<string, unknown>]>
    expect(updates.at(-1)?.[0]).toEqual(expect.objectContaining({
      baseMode: 'src_base',
      srcDs: 1,
      srcTable: 'src',
      tgtDs: 2,
      tgtTable: 'dst',
      fieldMap: [expect.objectContaining({ from: 'id', to: 'id' })],
    }))
  })

  it('uses the unified variable contract for sync text parameters and mapping expressions', async () => {
    const wrapper = mount(SyncMappingEditor, {
      props: {
        projectId: 7,
        workflowId: 11,
        workflowVersion: 1,
        taskId: 'sync_vars',
        modelValue: {
          source: { datasource_id: 1, schema: 'ods', object: 'src' },
          target: { datasource_id: 2, schema: 'dw', object: 'dst' },
          mappings: [{ source_column: 'id', target_column: 'id', transform_expression: '', nullable: true, default_value: null, mapping_status: 'AUTO' }],
        },
      },
      global: { stubs: { VariableReferenceInput: variableInputStub } },
    })

    await wrapper.get('[data-variable-field="filter-condition"]').trigger('click')
    await wrapper.get('[data-variable-field="mapping-transform-0"]').trigger('click')

    const updates = wrapper.emitted('update:modelValue') as Array<[Record<string, any>]>
    expect(updates.at(-1)?.[0].transform_config.filter_condition).toBe('${workflow.dynamic_value}')
    expect(updates.at(-1)?.[0].mappings[0].transform_expression).toBe('${workflow.dynamic_value}')
  })
})

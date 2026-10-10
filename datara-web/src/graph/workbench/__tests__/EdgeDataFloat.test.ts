// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EdgeDataFloat from '../EdgeDataFloat.vue'

const { listDefinitions, listInstancesPage, getInstanceDetail } = vi.hoisted(() => ({
  listDefinitions: vi.fn(),
  listInstancesPage: vi.fn(),
  getInstanceDetail: vi.fn(),
}))

vi.mock('../../../services', () => ({
  isMock: false,
  listDefinitions,
  listInstancesPage,
  getInstanceDetail,
}))

const doc = {
  id: 'wf-doc',
  name: 'Workflow',
  version: 1,
  meta: { profile: 'dag' },
  nodes: [],
  edges: [],
}

const edge = { id: 'e1', source: 'n1', target: 'n2' }
const upstream = { id: 'n1', type: 'sql', data: { name: 'SQL' }, position: { x: 0, y: 0 } }
const baseProps = {
  doc,
  edge,
  upstream,
  outputs: [{ name: 'result', type: 'table' }],
  dataType: 'table' as const,
}

describe('EdgeDataFloat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listDefinitions.mockResolvedValue([])
    listInstancesPage.mockResolvedValue({ list: [], total: 0 })
    getInstanceDetail.mockResolvedValue({ taskInstances: [] })
  })

  it('uses the known workflow code and caps the latest sample at 100 rows', async () => {
    listInstancesPage.mockResolvedValue({ list: [{ instanceId: 'run-1' }], total: 1 })
    getInstanceDetail.mockResolvedValue({
      taskInstances: [{
        nodeId: 'n1',
        outputs: {
          result_preview: {
            columns: ['id'],
            rows: Array.from({ length: 120 }, (_, index) => [index]),
          },
        },
      }],
    })

    const wrapper = mount(EdgeDataFloat, { props: { ...baseProps, workflowCode: 42 } })
    await flushPromises()

    expect(listDefinitions).not.toHaveBeenCalled()
    expect(listInstancesPage).toHaveBeenCalledWith({ wfCode: '42', pageSize: 1 })
    expect(wrapper.findAll('.sample-grid tbody tr')).toHaveLength(100)
  })

  it('renders schema only when no run record exists', async () => {
    const wrapper = mount(EdgeDataFloat, { props: { ...baseProps, workflowCode: 42 } })
    await flushPromises()

    expect(wrapper.find('.schema-list').exists()).toBe(true)
    expect(wrapper.find('.sample-section').exists()).toBe(false)
  })
})

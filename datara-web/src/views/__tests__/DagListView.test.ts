// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const listDefinitions = vi.hoisted(() => vi.fn())
const getUpgradeStatus = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('../../services', () => ({
  apiMode: 'api',
  isMock: false,
  listDefinitions,
  createDefinition: vi.fn(),
  deleteDefinition: vi.fn(),
  graphService: { get: vi.fn(), save: vi.fn() },
}))
vi.mock('../../services/templateApi', () => ({
  createTemplate: vi.fn(),
  getUpgradeStatus,
  listTemplates: vi.fn(),
  previewTemplateUpgrade: vi.fn(),
  instantiateTemplate: vi.fn(),
  confirmTemplateUpgrade: vi.fn(),
}))

import DagListView from '../DagListView.vue'
import WorkflowUpgradeActions from '../dag/WorkflowUpgradeActions.vue'

async function flush() {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
}

describe('DagListView template upgrade entry', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listDefinitions.mockResolvedValue([
      { id: 'wf_old', name: 'Old', version: 1, updatedAt: '2026-10-11T00:00:00' },
      { id: 'wf_current', name: 'Current', version: 2, updatedAt: '2026-10-11T00:00:00' },
    ])
    getUpgradeStatus.mockImplementation(async (id: string) => ({
      upgradeAvailable: id === 'wf_old',
      templateId: 7,
      currentVersion: id === 'wf_old' ? 1 : 2,
      latestVersion: 2,
    }))
  })

  it('loads and passes an independent upgrade status to every workflow row', async () => {
    const wrapper = mount(DagListView, { global: { stubs: { ScheduleDialog: true } } })
    await flush()

    expect(getUpgradeStatus).toHaveBeenCalledTimes(2)
    const actions = wrapper.findAllComponents(WorkflowUpgradeActions)
    expect(actions).toHaveLength(2)
    expect(actions.map((item) => item.props('workflowId'))).toEqual(['wf_old', 'wf_current'])
    expect(actions[0]!.props('status').upgradeAvailable).toBe(true)
    expect(actions[1]!.props('status').upgradeAvailable).toBe(false)
  })
})

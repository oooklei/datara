// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const impactedSpy = vi.hoisted(() => vi.fn())
const snapshotSpy = vi.hoisted(() => vi.fn())
const upgradeSpy = vi.hoisted(() => vi.fn())
vi.mock('../../../services/componentApi', () => ({
  getImpactedWorkflows: impactedSpy,
  getComponentVersionSnapshot: snapshotSpy,
  upgradeComponentRefs: upgradeSpy,
}))

import UpgradeWizard from '../UpgradeWizard.vue'

const oldSpec = { fields: [{ key: 'legacy_table', label: '旧表', uiType: 'text', required: false }] }
const newSpec = { fields: [{ key: 'source_table', label: '新表', uiType: 'text', required: false }] }

describe('UpgradeWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    impactedSpy.mockResolvedValue({
      type: 'comp_demo', publishedVersion: 2,
      items: [{ id: 'wf_a', name: '订单流', version: 4, releaseState: 'online', refVersions: [1], behind: true, aligned: false }],
    })
    snapshotSpy.mockImplementation((_type: string, version: number) => Promise.resolve({
      type: 'comp_demo', version, state: version === 1 ? 'offline' : 'published',
      spec: version === 1 ? oldSpec : newSpec, specHash: `hash-${version}`,
    }))
  })

  it('requires an explicit mapping or skip before submitting a breaking upgrade', async () => {
    const wrapper = mount(UpgradeWizard, { props: { componentType: 'comp_demo' } })
    await flushPromises()

    await wrapper.get('[data-testid="upgrade-next"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('字段变更')
    expect(wrapper.get('[data-testid="upgrade-submit"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="migration-skip-wf_a"]').setValue(true)
    expect(wrapper.get('[data-testid="upgrade-submit"]').attributes('disabled')).toBeUndefined()
    upgradeSpy.mockResolvedValue({ type: 'comp_demo', publishedVersion: 2, results: [{ wfId: 'wf_a', ok: true, migration: 'skip' }] })
    await wrapper.get('[data-testid="upgrade-submit"]').trigger('click')
    await flushPromises()

    expect(upgradeSpy).toHaveBeenCalledWith('comp_demo', [
      expect.objectContaining({ wfId: 'wf_a', baseVersion: 4, migration: 'skip' }),
    ])
    expect(wrapper.text()).toContain('明确跳过 1 项')
  })

  it('sends the chosen field mapping instead of an implicit migration guess', async () => {
    const wrapper = mount(UpgradeWizard, { props: { componentType: 'comp_demo' } })
    await flushPromises()
    await wrapper.get('[data-testid="upgrade-next"]').trigger('click')
    await flushPromises()

    await wrapper.get('select').setValue('source_table')
    upgradeSpy.mockResolvedValue({ type: 'comp_demo', publishedVersion: 2, results: [{ wfId: 'wf_a', ok: true, migration: 'map' }] })
    await wrapper.get('[data-testid="upgrade-submit"]').trigger('click')
    await flushPromises()

    expect(upgradeSpy).toHaveBeenCalledWith('comp_demo', [
      expect.objectContaining({
        wfId: 'wf_a', baseVersion: 4, migration: 'map', fieldMapping: { legacy_table: 'source_table' },
      }),
    ])
  })
})

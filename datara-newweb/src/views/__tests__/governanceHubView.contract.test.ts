import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GovernanceHubView from '../GovernanceHubView.vue'

describe('project governance hub', () => {
  it('exposes every formal E-group page and binds quality read-only tabs to their API kind', async () => {
    const wrapper = shallowMount(GovernanceHubView, {
      global: { stubs: { TabsView: false, KeepAlive: false } },
    })

    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.map((tab) => tab.attributes('data-tab-id'))).toEqual([
      'tag', 'std',
      'ind-list', 'ind-board', 'ind-consistency',
      'qc-rule', 'qc-task', 'qc-exception', 'qc-report', 'qc-alarm',
    ])

    const identities: object[] = []
    for (const [id, kind] of [
      ['qc-exception', 'exceptions'],
      ['qc-report', 'reports'],
      ['qc-alarm', 'alarms'],
    ] as const) {
      await wrapper.get(`[data-tab-id="${id}"]`).trigger('click')
      const view = wrapper.getComponent({ name: 'QualityReadOnlyView' })
      expect(view.attributes('kind')).toBe(kind)
      expect(view.vm.$.vnode.key).toBe(id)
      identities.push(view.vm)
    }
    expect(new Set(identities).size).toBe(3)
  })
})

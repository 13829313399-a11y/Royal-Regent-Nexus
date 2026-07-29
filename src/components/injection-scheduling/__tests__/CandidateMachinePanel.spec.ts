import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CandidateMachinePanel from '@/components/injection-scheduling/CandidateMachinePanel.vue'
import { cloneSchedulingSnapshot } from '@/data/injectionSchedulingMock'

describe('CandidateMachinePanel', () => {
  it('shows hard-constraint checks, scoring breakdown and assignment confirmation entry', async () => {
    const snapshot = cloneSchedulingSnapshot('huakang-b')!
    const order = snapshot.backlog.find((item) => item.candidates.length)!
    const wrapper = mount(CandidateMachinePanel, {
      props: { order, machines: snapshot.machines },
    })

    expect(wrapper.text()).toContain('候选机台与匹配解释')
    expect(wrapper.text()).toContain('模具长宽')
    expect(wrapper.text()).toContain('材料与螺杆')
    expect(wrapper.text()).toContain('查看评分分项')

    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('assign')?.[0]).toEqual([order.id, order.candidates[0]!.machineId])
  })

  it('explains why an order has no eligible machine', () => {
    const snapshot = cloneSchedulingSnapshot('huaxing')!
    const source = snapshot.backlog[0]!
    const order = { ...source, candidates: [], noMatchReason: '整啤毛重超过所有机台有效射胶量。' }
    const wrapper = mount(CandidateMachinePanel, {
      props: { order, machines: snapshot.machines },
    })
    expect(wrapper.text()).toContain('无合格候选机台')
    expect(wrapper.text()).toContain('整啤毛重超过')
  })
})

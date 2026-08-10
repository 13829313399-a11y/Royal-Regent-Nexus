import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ProductionReportPanel from '../components/ProductionReportPanel.vue'
import type { OrderRecord, ScheduleTaskRecord } from '../types'

const task = {
  id: 'task-1',
  planId: 'plan-1',
  machineId: 'machine-1',
  orderId: 'order-1',
  moldId: null,
  sequence: 0,
  status: 'QUEUED',
  plannedStart: '2026-08-10T08:00:00+08:00',
  plannedFinish: '2026-08-10T12:00:00+08:00',
  targetQuantity: 3000,
  reportedQuantity: 0,
  sourceSheetName: '',
  sourceRow: null,
  locked: false,
  manualOverrideReason: '',
  activeExecution: true,
  estimatedStart: '2026-08-10T08:00:00+08:00',
  estimatedFinish: '2026-08-10T12:00:00+08:00',
  estimatedRemainingShifts: 1,
  deliverySlackDays: 0,
  revision: 1,
} as ScheduleTaskRecord

const order = {
  id: 'order-1',
  orderQuantity: 3000,
  completedQuantity: 0,
  sourceCompletedQuantity: 0,
  completionRate: 0,
  revision: 1,
} as OrderRecord

describe('生产回报面板', () => {
  it('修改状态后自动加入待保存，不再要求额外点击加入批量保存', async () => {
    const wrapper = mount(ProductionReportPanel, {
      props: {
        task,
        order,
        planStatus: 'PUBLISHED',
        canReport: true,
        pendingCount: 0,
        saving: false,
      },
    })

    expect(wrapper.text()).not.toContain('加入批量保存')
    const status = wrapper.find('select')
    await status.setValue('RUNNING')

    const staged = wrapper.emitted('stage')
    expect(staged).toHaveLength(1)
    expect(staged?.[0]?.[0]).toContainEqual({ key: 'status', value: 'RUNNING' })

    await wrapper.setProps({ pendingCount: 1 })
    const save = wrapper.find('button.primary')
    expect(save.text()).toContain('保存生产回报（1项修改）')
    expect(save.attributes('disabled')).toBeUndefined()
    await save.trigger('click')
    expect(wrapper.emitted('save')).toHaveLength(1)
  })
})

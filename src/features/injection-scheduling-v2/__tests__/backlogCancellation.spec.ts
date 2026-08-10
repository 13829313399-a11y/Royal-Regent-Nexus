import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import BacklogOrderCancelDialog from '../components/BacklogOrderCancelDialog.vue'
import type { OrderRecord } from '../types'

const root = join(process.cwd(), 'src/features/injection-scheduling-v2')
const viewSource = readFileSync(join(root, 'InjectionSchedulingV2View.vue'), 'utf8')
const dockSource = readFileSync(join(root, 'components/BacklogDock.vue'), 'utf8')
const apiSource = readFileSync(join(root, 'api/injectionSchedulingV2Api.ts'), 'utf8')
const storeSource = readFileSync(join(root, 'stores/useInjectionSchedulingV2Store.ts'), 'utf8')

const order: OrderRecord = {
  id: 'order-backlog-1', orderNo: 'FBE202500203', itemNo: '50002010', productName: '30寸黑武士-配件',
  moldId: null, moldDefinitionId: 'definition-1', moldOutputSpecId: 'output-1', orderQuantity: 800,
  sourceCompletedQuantity: 0, completedQuantity: 0, outstandingQuantity: 800, completionRate: 0,
  deliveryStartDate: '', deliveryDueDate: '2026-08-03', deliverySlackDays: -7,
  priorityCode: 'NORMAL', materialReadinessStatus: 'ready', warehouseText: '', remark: '',
  sourceType: 'DEMAND_ORDER_VERSION', status: 'BACKLOG', lineage: {}, revision: 2,
}

describe('待排订单删除', () => {
  it('requires an explicit reason and explains that source history is retained', async () => {
    const wrapper = mount(BacklogOrderCancelDialog, {
      global: { stubs: { Teleport: true } },
      props: { open: true, order, canCancel: true, cancelling: false, error: '' },
    })
    expect(wrapper.text()).toContain('删除待排单')
    expect(wrapper.text()).toContain('原下单表、订单版本和操作记录会保留')
    const confirm = wrapper.findAll('button').find((item) => item.text().includes('确认删除待排单'))!
    expect((confirm.element as HTMLButtonElement).disabled).toBe(true)
    await wrapper.find('textarea').setValue('重复下单')
    await wrapper.vm.$nextTick()
    const enabledConfirm = wrapper.findAll('button').find((item) => item.text().includes('确认删除待排单'))!
    expect((enabledConfirm.element as HTMLButtonElement).disabled).toBe(false)
    await enabledConfirm.trigger('click')
    expect(wrapper.emitted('confirm')).toEqual([['重复下单']])
  })

  it('exposes the action in both backlog views and revision-protects the API call', () => {
    expect(viewSource).toContain('@click="openBacklogCancel(order.id)"')
    expect(dockSource).toContain("emit('delete', order.id)")
    expect(apiSource).toContain('/backlog/${order.id}/cancel')
    expect(apiSource).toContain('expected_plan_revision: planningPlan?.revision ?? null')
    expect(storeSource).toContain('原始下单和审计记录已保留')
  })
})

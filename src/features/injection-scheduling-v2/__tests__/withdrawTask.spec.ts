import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import WithdrawTaskDialog from '../components/WithdrawTaskDialog.vue'
import type { OrderRecord, ScheduleTaskRecord } from '../types'

const root = join(process.cwd(), 'src/features/injection-scheduling-v2')
const apiSource = readFileSync(join(root, 'api/injectionSchedulingV2Api.ts'), 'utf8')
const storeSource = readFileSync(join(root, 'stores/useInjectionSchedulingV2Store.ts'), 'utf8')

const order: OrderRecord = {
  id: 'order-1', orderNo: 'BJB251306', itemNo: '20 330 2017', productName: '车底组件',
  moldId: null, moldDefinitionId: null, moldOutputSpecId: null, orderQuantity: 3000,
  sourceCompletedQuantity: 0, completedQuantity: 0, outstandingQuantity: 3000, completionRate: 0,
  deliveryStartDate: '', deliveryDueDate: '2026-08-03', deliverySlackDays: -7,
  priorityCode: 'NORMAL', materialReadinessStatus: 'ready', warehouseText: '', remark: '',
  sourceType: 'DEMAND_ORDER_VERSION', status: 'SCHEDULED', lineage: {}, revision: 1,
}

const task: ScheduleTaskRecord = {
  id: 'task-1', planId: 'plan-1', machineId: 'machine-1', orderId: order.id, moldId: null,
  sequence: 0, status: 'RUNNING', plannedStart: '2026-08-09T08:00:00+08:00',
  plannedFinish: '2026-08-10T05:11:00+08:00', targetQuantity: 3000, reportedQuantity: 0,
  sourceSheetName: '下单表', sourceRow: 4, locked: false, manualOverrideReason: '', activeExecution: true,
  estimatedStart: '', estimatedFinish: '', estimatedRemainingShifts: 0, deliverySlackDays: -7, revision: 1,
}

describe('已排任务撤回待排', () => {
  it('解释发布计划的草案语义，并要求填写撤回原因', async () => {
    const wrapper = mount(WithdrawTaskDialog, {
      global: { stubs: { Teleport: true } },
      props: {
        open: true, task, order, planStatus: 'PUBLISHED', canWithdraw: true,
        disabledReason: '', withdrawing: false, error: '',
      },
    })
    expect(wrapper.text()).toContain('撤回订单到待排池')
    expect(wrapper.text()).toContain('正式计划暂不改变')
    const confirm = wrapper.findAll('button').find((item) => item.text().includes('确认撤回待排'))!
    expect(confirm.attributes('disabled')).toBeDefined()
    await wrapper.find('textarea').setValue('订单暂停')
    await wrapper.vm.$nextTick()
    const enabledConfirm = wrapper.findAll('button').find((item) => item.text().includes('确认撤回待排'))!
    expect((enabledConfirm.element as HTMLButtonElement).disabled).toBe(false)
    await enabledConfirm.trigger('click')
    expect(wrapper.emitted('confirm')).toEqual([['订单暂停']])
  })

  it('调用带版本校验的撤回接口并切换到规划草案', () => {
    expect(apiSource).toContain('/withdraw-to-backlog')
    expect(apiSource).toContain('expected_task_revision')
    expect(apiSource).toContain('expected_planning_revision')
    expect(storeSource).toContain("activatePlanSlice('planning', true)")
    expect(storeSource).toContain('调整已写入规划草案，发布后替换正式计划')
  })
})

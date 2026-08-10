import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AutoSchedulePreviewDialog from '../components/AutoSchedulePreviewDialog.vue'
import ScheduleRunHistory from '../components/ScheduleRunHistory.vue'
import type { AutoScheduleRunRecord, MachineRecord, OrderRecord } from '../types'

const order: OrderRecord = {
  id: 'order-1', orderNo: 'SO-001', itemNo: 'ITEM-1', productName: '测试件', moldId: 'mold-1',
  orderQuantity: 100, sourceCompletedQuantity: 0, completedQuantity: 0, outstandingQuantity: 100,
  completionRate: 0, deliveryStartDate: '2026-08-04', deliveryDueDate: '2026-08-08', deliverySlackDays: 4,
  priorityCode: 'URGENT', materialReadinessStatus: 'ready', warehouseText: '', remark: '', status: 'BACKLOG', lineage: {}, revision: 1,
}
const machine: MachineRecord = {
  id: 'machine-1', code: '新25', position: '25', area: '注塑车间', aClass: 12, aClassRaw: '12A',
  injectionCapacityG: 217, armCapabilities: ['dual'], fixtureCapabilities: ['suction_cup'], processRestrictions: [],
  machineType: 'standard', specialMachineType: '', status: 'available', normalizationStatus: 'COMPLETE',
}
const run: AutoScheduleRunRecord = {
  id: 'run-1', factoryId: 'huaxing', planId: 'plan-1', expectedPlanRevision: 3, ruleRevision: 1,
  solverType: 'HEURISTIC', requestedSolver: 'HEURISTIC', solverVersion: 'phase3-v1', solverStatus: 'HEURISTIC', fallbackUsed: false, fallbackReason: '',
  scenarioGroupId: 'scenario-1', scenarioName: '方案 A · 综合平衡', alternativeNo: 1, replayOfRunId: null,
  objectiveWeights: { tardinessWeight: 100, transitionWeight: 2, classGapWeight: 1.5, loadBalanceWeight: 25, existingTaskMoveCost: 40 },
  status: 'PARTIAL', horizonStart: '2026-08-04T08:00:00+08:00', horizonEnd: '2026-08-18T20:00:00+08:00',
  summary: {
    inputOrderCount: 2, scheduledCount: 1, reviewCount: 1, unassignedCount: 0, movedTaskCount: 0, localImprovementMoveCount: 0, frozenTaskCount: 1,
    overdue: { before: 2, after: 1, change: -1 }, moldChanges: { before: 3, after: 2, change: -1 },
    darkToLightChanges: { before: 1, after: 0, change: -1 }, machineLoads: [{ machineId: 'machine-1', machineCode: '新25', scheduledMinutes: 240, loadRatio: 0.25 }], solverElapsedMs: 12.4,
    solverStatus: 'HEURISTIC', objectiveValue: null, bestObjectiveBound: null, fallbackUsed: false, fallbackReason: '',
  },
  errorDetail: '', createdByName: '计划员', createdAt: '2026-08-04T09:00:00+08:00', appliedByName: '', appliedAt: '',
  assignments: [{
    id: 'assignment-1', orderId: 'order-1', existingTaskId: null, moldId: 'mold-1', moldCopyNo: 1,
    machineId: 'machine-1', sequence: 1, plannedStart: '2026-08-04T08:00:00+08:00', plannedFinish: '2026-08-04T12:00:00+08:00',
    setupMinutes: 30, productionMinutes: 210, plannedDowntimeMinutes: 0, changeoverType: 'MOLD', decision: 'REVIEW_REQUIRED', score: 42,
    explanation: { summary: '当前窗口安排 72,000，剩余 128,004 继续留在待排订单。', production: { capacity_source: 'SOURCE_DAILY_CAPACITY', planned_quantity: 72000, remaining_quantity: 128004, production_minutes: 20736 }, hard_checks: [{ code: 'ELIGIBILITY_PASS', label: '硬约束', detail: '无硬失败' }], score_breakdown: [{ code: 'transition', detail: '换模 30 分钟', cost: 60 }] },
    unassignedReasonCode: '',
  }],
}

describe('Phase 3 自动排期预览', () => {
  it('展示指标、负荷和逐条解释，并强制待复核覆盖原因', async () => {
    const wrapper = mount(AutoSchedulePreviewDialog, {
      global: { stubs: { Teleport: true } },
      props: {
        open: true, backlogCount: 2, machineCount: 1, planStatus: 'DRAFT', canEdit: true,
        canOverride: true, run, loading: false, error: '', orders: [order], machines: [machine],
      },
    })
    expect(wrapper.text()).toContain('预计超期')
    expect(wrapper.text()).toContain('2 → 1（-1）')
    expect(wrapper.text()).toContain('目标值 / 下界')
    expect(wrapper.text()).toContain('机台负荷')
    expect(wrapper.text()).toContain('SO-001')
    expect(wrapper.text()).toContain('下单表模具日产量')
    expect(wrapper.text()).toContain('本窗口安排')
    expect(wrapper.text()).toContain('72,000')
    expect(wrapper.text()).toContain('窗口后待排')
    expect(wrapper.text()).toContain('128,004')
    const applyButton = wrapper.findAll('button').find((item) => item.text().includes('应用到草案'))!
    expect(applyButton.attributes('disabled')).toBeDefined()
    await wrapper.find('textarea').setValue('主管确认资料可覆盖')
    expect(applyButton.attributes('disabled')).toBeUndefined()
    await applyButton.trigger('click')
    expect(wrapper.emitted('apply')?.[0]).toEqual(['主管确认资料可覆盖'])
  })

  it('运行历史可回看持久化方案', async () => {
    const wrapper = mount(ScheduleRunHistory, { props: { runs: [run] } })
    expect(wrapper.text()).toContain('部分完成')
    expect(wrapper.text()).toContain('排 1 · 核 1 · 未 0')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toEqual(run)
  })
})

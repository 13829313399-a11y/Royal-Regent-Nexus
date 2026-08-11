import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AutoSchedulePreviewDialog from '../components/AutoSchedulePreviewDialog.vue'
import RevisionConflictDialog from '../components/RevisionConflictDialog.vue'
import TaskInspectorDrawer from '../components/TaskInspectorDrawer.vue'
import type { AuditEvent, AutoScheduleRunRecord, RevisionConflict } from '../types'
import { createSchedulingBaselineFixture } from './fixtures/schedulingBaselineFixture'

const autoRun: AutoScheduleRunRecord = {
  id: 'b4a-run', factoryId: 'huaxing', planId: 'b4a-plan', expectedPlanRevision: 9, ruleRevision: 4,
  solverType: 'CP_SAT', requestedSolver: 'CP_SAT', solverVersion: 'b4a-solver-v1', solverStatus: 'OPTIMAL',
  fallbackUsed: false, fallbackReason: '', scenarioGroupId: 'b4a-group', scenarioName: '方案 A · 综合平衡',
  alternativeNo: 1, replayOfRunId: null,
  objectiveWeights: { tardinessWeight: 100, transitionWeight: 2, classGapWeight: 1.5, loadBalanceWeight: 25, existingTaskMoveCost: 40 },
  status: 'SUCCEEDED', horizonStart: '2026-08-11T08:00:00+08:00', horizonEnd: '2026-08-18T20:00:00+08:00',
  summary: {
    inputOrderCount: 9, scheduledCount: 6, reviewCount: 2, unassignedCount: 1, movedTaskCount: 2,
    localImprovementMoveCount: 1, frozenTaskCount: 3,
    overdue: { before: 4, after: 1, change: -3 }, moldChanges: { before: 8, after: 5, change: -3 },
    darkToLightChanges: { before: 2, after: 1, change: -1 },
    machineLoads: [{ machineId: 'machine-1', machineCode: '新25', scheduledMinutes: 480, loadRatio: 0.625 }],
    solverElapsedMs: 2_480, solverStatus: 'OPTIMAL', objectiveValue: 128.5, bestObjectiveBound: 128.5,
    fallbackUsed: false, fallbackReason: '',
    continuationAnchors: [{ machineId: 'machine-1', startsAt: '2026-08-11T08:00:00+08:00', sources: [{ source: 'published' }] }],
  },
  errorDetail: '', createdByName: '计划员', createdAt: '2026-08-11T09:00:00+08:00',
  appliedByName: '', appliedAt: '', assignments: [],
}

const autoProps = {
  open: true,
  backlogCount: 9,
  machineCount: 4,
  planStatus: 'DRAFT',
  canEdit: true,
  canOverride: true,
  run: null,
  comparisonRuns: [],
  loading: false,
  error: '',
  orders: [],
  machines: [],
}

describe('B4a complex business information layering', () => {
  it('keeps three business presets visible and preserves the selected generation payload', async () => {
    const wrapper = mount(AutoSchedulePreviewDialog, {
      global: { stubs: { Teleport: true } },
      props: autoProps,
    })

    const presets = wrapper.get('.business-preset-grid')
    expect(presets.text()).toContain('综合平衡')
    expect(presets.text()).toContain('交期优先')
    expect(presets.text()).toContain('少换模')
    expect(wrapper.get('details.optimization-details').attributes('open')).toBeUndefined()
    expect(wrapper.get('details.optimization-details').text()).toContain('优化求解')
    expect(wrapper.get('details.optimization-details').text()).toContain('自定义权重')

    await wrapper.get('[data-preset="due"]').trigger('click')
    await wrapper.findAll('button').find((button) => button.text().includes('生成选定方案'))!.trigger('click')

    expect(wrapper.emitted('generate')?.[0]?.[0]).toEqual({
      solver: 'CP_SAT',
      scenarioName: '方案 B · 交期优先',
      objectiveWeights: { tardinessWeight: 220, transitionWeight: 1, classGapWeight: 1, loadBalanceWeight: 10, existingTaskMoveCost: 30 },
    })
  })

  it('uses one honest indeterminate loading message and separates business results from optimization diagnostics', () => {
    const loadingWrapper = mount(AutoSchedulePreviewDialog, {
      global: { stubs: { Teleport: true } },
      props: { ...autoProps, loading: true },
    })
    expect(loadingWrapper.get('[role="status"]').text()).toContain('正在检查条件并生成排产方案…')
    expect(loadingWrapper.get('[role="status"]').text()).not.toMatch(/\d+%|候选阶段|求解阶段/)

    const resultWrapper = mount(AutoSchedulePreviewDialog, {
      global: { stubs: { Teleport: true } },
      props: { ...autoProps, run: autoRun },
    })
    const businessLayer = resultWrapper.get('.business-result-layer')
    expect(businessLayer.text()).toContain('预计超期')
    expect(businessLayer.text()).toContain('换模次数')
    expect(businessLayer.text()).toContain('待复核')
    expect(businessLayer.text()).toContain('未安排')
    expect(businessLayer.text()).toContain('机台负荷')
    expect(businessLayer.text()).not.toContain('CP_SAT')
    expect(businessLayer.text()).not.toContain('OPTIMAL')
    expect(businessLayer.text()).not.toContain('目标下界')

    const optimization = resultWrapper.get('details.optimization-details')
    expect(optimization.attributes('open')).toBeUndefined()
    expect(optimization.get('.scheduling-technical-details dl').text()).toContain('CP_SAT')
    expect(optimization.get('.scheduling-technical-details dl').text()).toContain('OPTIMAL')
    expect(optimization.get('.scheduling-technical-details dl').text()).toContain('目标下界')
  })

  it('keeps the task inspector business-first and folds raw task and audit diagnostics', async () => {
    const fixture = createSchedulingBaselineFixture(1, 1)
    const task = {
      ...fixture.tasks[0]!,
      profileId: 'huakang-b-schedule',
      profileRevision: 7,
      manualOverrideReason: '夹具资料需主管确认',
      autoExplanation: {
        decision: 'REVIEW_REQUIRED',
        summary: '夹具资料待确认，当前安排需要人工复核。',
        calculation: {
          continuation_anchor: '2026-08-11T08:00:00+08:00',
          calculation_version: 'canonical-v3',
          speed_source: 'ACTIVE_SPEED_MODEL',
        },
      },
    }
    const event: AuditEvent = {
      id: 'audit-1', sequence: 42, eventType: 'plan_task_updated', entityType: 'task', entityId: task.id,
      entityRevision: 8, requestId: 'request-b4a-42', actorName: '计划员', createdAt: '2026-08-11 09:30', detail: { changed: ['plannedFinish'] },
    }
    const wrapper = mount(TaskInspectorDrawer, {
      props: {
        task, order: fixture.orders[0]!, mold: fixture.molds[0]!, machine: fixture.machines[0]!, tab: 'order',
        events: [event], planStatus: 'DRAFT', canReport: true, canWithdraw: true, withdrawDisabledReason: '',
        withdrawing: false, pendingCount: 0, saving: false,
      },
    })

    const business = wrapper.get('.inspector-business-details')
    expect(business.text()).toContain('模具与机台')
    expect(business.text()).toContain('欠数 / 目标数')
    expect(business.text()).toContain('生产进度')
    expect(business.text()).toContain('需要人工复核')
    expect(business.text()).not.toContain('Profile')
    expect(business.text()).not.toContain('canonical-v3')
    expect(business.text()).not.toContain('ACTIVE_SPEED_MODEL')

    const taskTechnical = wrapper.get('.inspector-technical-details')
    expect(taskTechnical.attributes('open')).toBeUndefined()
    expect(taskTechnical.get('dl').text()).toContain('huakang-b-schedule')
    expect(taskTechnical.get('dl').text()).toContain('canonical-v3')
    expect(taskTechnical.get('dl').text()).toContain('ACTIVE_SPEED_MODEL')

    await wrapper.setProps({ tab: 'history' })
    expect(wrapper.get('.history-event-business').text()).toContain('任务安排已更新')
    expect(wrapper.get('.history-event-business').text()).not.toContain('plan_task_updated')
    expect(wrapper.get('.history-event-technical dl').text()).toContain('plan_task_updated')
    expect(wrapper.get('.history-event-technical dl').text()).toContain('42')
    expect(wrapper.get('.history-event-technical dl').text()).toContain('request-b4a-42')
  })

  it('uses business field names in revision conflict columns while retaining raw keys in technical details', async () => {
    const conflict: RevisionConflict = {
      title: 'Task revision conflict',
      message: 'expected revision 7 but found revision 8',
      localValues: {
        machineId: 'machine-new', moldId: 'mold-new', sequence: 3, targetQuantity: 1_200,
        plannedFinish: '2026-08-12 18:00', manualOverrideReason: '主管确认插单',
      },
      serverValues: { machineId: 'machine-current', moldId: 'mold-current', sequence: 4, targetQuantity: 1_000 },
      retry: async () => undefined,
    }
    const wrapper = mount(RevisionConflictDialog, {
      global: { stubs: { Teleport: true } },
      props: { conflict, loading: false },
    })

    const columns = wrapper.get('.conflict-columns')
    expect(columns.text()).toContain('安排机台')
    expect(columns.text()).toContain('使用模具')
    expect(columns.text()).toContain('机台内顺序')
    expect(columns.text()).toContain('计划目标数')
    expect(columns.text()).toContain('人工调整原因')
    expect(columns.text()).not.toContain('machineId')
    expect(columns.text()).not.toContain('manualOverrideReason')
    expect(wrapper.get('.scheduling-technical-details dl').text()).toContain('machineId')
    expect(wrapper.get('.scheduling-technical-details dl').text()).toContain('manualOverrideReason')

    await wrapper.findAll('footer button')[0]!.trigger('click')
    await wrapper.findAll('footer button')[1]!.trigger('click')
    expect(wrapper.emitted('useServer')).toHaveLength(1)
    expect(wrapper.emitted('reapply')).toHaveLength(1)
  })
})

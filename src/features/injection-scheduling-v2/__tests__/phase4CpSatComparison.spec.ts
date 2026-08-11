import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AutoSchedulePreviewDialog from '../components/AutoSchedulePreviewDialog.vue'
import type { AutoScheduleRunRecord } from '../types'

const baseRun: AutoScheduleRunRecord = {
  id: 'cp-run-a', factoryId: 'huaxing', planId: 'plan-1', expectedPlanRevision: 3, ruleRevision: 1,
  solverType: 'CP_SAT', requestedSolver: 'CP_SAT', solverVersion: 'phase4-cp-sat-v1', solverStatus: 'OPTIMAL', fallbackUsed: false, fallbackReason: '',
  scenarioGroupId: 'scenario-cp', scenarioName: '方案 A · 综合平衡', alternativeNo: 1, replayOfRunId: null,
  objectiveWeights: { tardinessWeight: 100, transitionWeight: 2, classGapWeight: 1.5, loadBalanceWeight: 25, existingTaskMoveCost: 40 },
  status: 'SUCCEEDED', horizonStart: '2026-08-04T08:00:00+08:00', horizonEnd: '2026-08-18T20:00:00+08:00',
  summary: {
    inputOrderCount: 2, scheduledCount: 2, reviewCount: 0, unassignedCount: 0, movedTaskCount: 0, localImprovementMoveCount: 0, frozenTaskCount: 1,
    overdue: { before: 2, after: 0, change: -2 }, moldChanges: { before: 3, after: 1, change: -2 }, darkToLightChanges: { before: 1, after: 0, change: -1 },
    machineLoads: [], solverElapsedMs: 42, solverStatus: 'OPTIMAL', objectiveValue: 120, bestObjectiveBound: 120, fallbackUsed: false, fallbackReason: '',
  },
  errorDetail: '', createdByName: '计划员', createdAt: '2026-08-04T09:00:00+08:00', appliedByName: '', appliedAt: '', assignments: [],
}
const dueRun: AutoScheduleRunRecord = { ...baseRun, id: 'cp-run-b', scenarioName: '方案 B · 交期优先', alternativeNo: 2, summary: { ...baseRun.summary, objectiveValue: 180, moldChanges: { before: 3, after: 2, change: -1 } } }

describe('Phase 4 CP-SAT 多方案', () => {
  it('生成页暴露求解器、权重和三方案入口', async () => {
    const wrapper = mount(AutoSchedulePreviewDialog, { global: { stubs: { Teleport: true } }, props: { open: true, backlogCount: 8, machineCount: 4, planStatus: 'DRAFT', canEdit: true, canOverride: true, run: null, comparisonRuns: [], loading: false, error: '', orders: [], machines: [] } })
    expect(wrapper.text()).toContain('优化求解')
    expect(wrapper.text()).toContain('校验机台与模具占用')
    expect(wrapper.get('option[value="CP_SAT"]').attributes('value')).toBe('CP_SAT')
    await wrapper.findAll('button').find((item) => item.text().includes('生成三套方案'))!.trigger('click')
    expect(wrapper.emitted('compare')).toHaveLength(1)
  })

  it('对比方案并支持按保存权重回放', async () => {
    const wrapper = mount(AutoSchedulePreviewDialog, { global: { stubs: { Teleport: true } }, props: { open: true, backlogCount: 2, machineCount: 2, planStatus: 'DRAFT', canEdit: true, canOverride: true, run: baseRun, comparisonRuns: [baseRun, dueRun], loading: false, error: '', orders: [], machines: [] } })
    expect(wrapper.get('.run-banner').text()).toContain('方案 A · 综合平衡')
    expect(wrapper.get('.run-banner').text()).not.toContain('CP_SAT')
    expect(wrapper.get('.optimization-result-overview').text()).toContain('优化求解 · 模型目标下已找到最优结果')
    expect(wrapper.get('.scheduling-technical-details dl').text()).toContain('CP_SAT')
    expect(wrapper.get('.scheduling-technical-details dl').text()).toContain('OPTIMAL')
    expect(wrapper.text()).toContain('方案 B · 交期优先')
    await wrapper.findAll('.scenario-strip button')[1]!.trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toEqual(dueRun)
    await wrapper.findAll('button').find((item) => item.text().includes('按此权重回放'))!.trigger('click')
    expect(wrapper.emitted('replay')?.[0]?.[0]).toEqual(baseRun)
  })
})

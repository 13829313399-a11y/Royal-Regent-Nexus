import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import Phase5OperationsDashboard from '../components/Phase5OperationsDashboard.vue'
import SchedulingCommandBar from '../components/SchedulingCommandBar.vue'
import SchedulingKpiStrip from '../components/SchedulingKpiStrip.vue'
import type { Phase5AnalyticsRecord } from '../types'

const metric = (value: number, unit: string, formula: string) => ({ value, numerator: value, denominator: 10, unit, sampleCount: 10, formula })
const analytics: Phase5AnalyticsRecord = {
  factoryId: 'huaxing', dateFrom: '2026-07-06', dateTo: '2026-08-04', generatedAt: '2026-08-04T10:00:00+08:00',
  planAccuracy: metric(92.5, '%', '按期完成任务 / 已完成任务'),
  moldChangeCount: metric(7, '次', '同机相邻任务模具变化'),
  overdueRate: metric(8.2, '%', '超期订单 / 应交订单'),
  machineUtilization: metric(74.1, '%', '设备运行分钟 / 可用机台分钟'),
  integrationStatuses: [
    { sourceType: 'ERP', sourceKey: 'default', cursor: '20260804-10', status: 'ACTIVE', lastReceivedAt: '2026-08-04T10:00:00+08:00', lastSuccessAt: '2026-08-04T10:00:00+08:00', lastError: '', eventCount: 12, revision: 3 },
    { sourceType: 'DEVICE', sourceKey: 'default', cursor: '', status: 'NOT_CONFIGURED', lastReceivedAt: '', lastSuccessAt: '', lastError: '', eventCount: 0, revision: 0 },
  ],
  speedModels: [{ id: 'speed-1', factoryId: 'huaxing', moldId: 'mold-1', moldNo: 'M-100', sampleCount: 8, calibratedCycleSeconds: 42, unitsPerCycle: 2, calibratedUnitsPerHour: 171.4, confidence: 0.8, status: 'ACTIVE', sourceWindowStart: '2026-08-01T08:00:00+08:00', sourceWindowEnd: '2026-08-04T08:00:00+08:00', lastObservedAt: '2026-08-04T08:00:00+08:00', revision: 1, updatedAt: '2026-08-04T10:00:00+08:00' }],
  deviceInterfaceConfigured: false,
  notes: ['计划达成率只统计已完成任务。'],
}

describe('Phase 5 运营分析', () => {
  it('展示指标、接口状态和已启用速度模型', () => {
    const wrapper = mount(Phase5OperationsDashboard, { props: { analytics, loading: false, error: '', canManageRules: true } })
    expect(wrapper.text()).toContain('计划达成率')
    expect(wrapper.text()).toContain('92.5%')
    expect(wrapper.text()).toContain('ERP 新单增量同步')
    expect(wrapper.text()).toContain('未配置接口')
    expect(wrapper.text()).toContain('M-100')
    expect(wrapper.text()).toContain('已启用')
  })

  it('刷新始终可用，校准受规则管理权限控制', async () => {
    const wrapper = mount(Phase5OperationsDashboard, { props: { analytics, loading: false, error: '', canManageRules: false } })
    const refresh = wrapper.findAll('button').find((button) => button.text().includes('刷新'))!
    const calibrate = wrapper.findAll('button').find((button) => button.text().includes('重新校准'))!
    expect(calibrate.attributes('disabled')).toBeDefined()
    await refresh.trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('使用正式业务标识并保持明确的超期口径', () => {
    const commandBar = mount(SchedulingCommandBar, { global: { plugins: [createPinia()] }, props: { factoryId: 'huaxing', factoryName: '华兴', sourceMode: 'live', sourceMessage: '正式数据库', refreshing: false, search: '', lastSyncedAt: '', planStatus: '', pendingCount: 0, saving: false, canSave: true, saveMessage: '' } })
    const kpis = mount(SchedulingKpiStrip, { props: { summary: { availableMachines: 1, totalMachines: 1, scheduledTasks: 1, runningTasks: 0, overdue: 1, dueSoon: 0, remaining: 0, completeness: 100, backlog: 0, review: 0 } } })
    expect(commandBar.text()).toContain('智能优化引擎')
    expect(commandBar.text()).not.toContain('Phase 5')
    expect(kpis.text()).toContain('已超交期')
    expect(kpis.text()).not.toContain('已经交期')
  })
})

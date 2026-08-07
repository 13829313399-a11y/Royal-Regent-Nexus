import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import InjectionSchedulingImportWizard from '../components/InjectionSchedulingImportWizard.vue'
import ScheduleTimeline from '../components/ScheduleTimeline.vue'

const root = join(process.cwd(), 'src/features/injection-scheduling-v2')
const apiSource = readFileSync(join(root, 'api/injectionSchedulingV2Api.ts'), 'utf8')
const storeSource = readFileSync(join(root, 'stores/useInjectionSchedulingV2Store.ts'), 'utf8')
const viewSource = readFileSync(join(root, 'InjectionSchedulingV2View.vue'), 'utf8')

describe('注塑排产公共计划 Phase 4 工作流', () => {
  it('提供独立导入向导并在只读模式禁止上传', () => {
    const wrapper = mount(InjectionSchedulingImportWizard, {
      props: { open: true, factoryId: 'huaxing', businessDate: '2026-08-07', canImport: false, canManageMaster: false, sourceMode: 'fallback' },
    })
    expect(wrapper.text()).toContain('导入计划表')
    expect(wrapper.text()).not.toContain('恢复最近批次')
    expect(wrapper.text()).toContain('当前为只读模式')
    expect(wrapper.get('button.wizard-primary').attributes('disabled')).toBeDefined()
  })

  it('显式保存 execution/planning 两个切片及其独立 UI 状态', () => {
    expect(storeSource).toContain('executionPublishedPlan')
    expect(storeSource).toContain('planningDraftPlan')
    expect(storeSource).toContain('activePlanSlice')
    expect(storeSource).toContain('timelineScrollLeft')
    expect(storeSource).toContain('cellDrafts.value = { ...target.cellDrafts }')
    expect(viewSource).toContain("activatePlanSlice('execution')")
    expect(viewSource).toContain("activatePlanSlice('planning')")
    expect(apiSource).toContain('/injection-scheduling/imports/${batch.id}/retry')
    expect(apiSource).toContain("'Content-Type': 'multipart/form-data'")
    expect(apiSource).toContain('/manual-append/preview')
    expect(apiSource).toContain('/manual-append/confirm')
  })

  it('按业务日和有效任务动态生成跨月时间轴并暴露坏数据', () => {
    const wrapper = mount(ScheduleTimeline, {
      props: {
        businessDate: '2026-12-28',
        scrollLeft: 0,
        zoom: 1,
        machines: [{ id: 'm1', code: '1号机', position: '', area: '', aClass: 7, aClassRaw: '7A', injectionCapacityG: 200, armCapabilities: [], fixtureCapabilities: [], processRestrictions: [], machineType: 'standard', specialMachineType: '', status: 'available', normalizationStatus: 'COMPLETE' }],
        orders: [],
        tasks: [
          { id: 'valid', planId: 'p1', machineId: 'm1', orderId: 'o1', moldId: null, sequence: 0, status: 'QUEUED', plannedStart: '2027-01-15T08:00:00', plannedFinish: '2027-01-15T12:00:00', targetQuantity: 40, reportedQuantity: 0, sourceSheetName: '', sourceRow: null, locked: false, manualOverrideReason: '', activeExecution: false, estimatedStart: '', estimatedFinish: '', estimatedRemainingShifts: 1, deliverySlackDays: null, revision: 1 },
          { id: 'invalid', planId: 'p1', machineId: 'm1', orderId: 'o2', moldId: null, sequence: 1, status: 'QUEUED', plannedStart: 'bad', plannedFinish: '', targetQuantity: 40, reportedQuantity: 0, sourceSheetName: '', sourceRow: null, locked: false, manualOverrideReason: '', activeExecution: false, estimatedStart: '', estimatedFinish: '', estimatedRemainingShifts: 1, deliverySlackDays: null, revision: 1 },
        ],
      },
    })
    expect(wrapper.text()).toContain('2026-12-28')
    expect(wrapper.text()).toContain('2027-01-15')
    expect(wrapper.text()).toContain('1 个任务的计划起止无效')
    expect(wrapper.findAll('.timeline-track button')).toHaveLength(1)
  })
})

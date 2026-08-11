import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import EligibilityChecks from '../components/EligibilityChecks.vue'
import InjectionSchedulingExportDialog from '../components/InjectionSchedulingExportDialog.vue'
import Phase5OperationsDashboard from '../components/Phase5OperationsDashboard.vue'
import * as labels from '../presentation/schedulingLabels'
import type { MachineRecord, MoldRecord, Phase5AnalyticsRecord, SchedulingPlanRecord } from '../types'

const label = (name: string, code: string) => (labels as unknown as Record<string, (value: unknown) => { code: string; label: string; cssToken: string }>)[name]?.(code)

const plan: SchedulingPlanRecord = {
  id: 'plan-1', status: 'DRAFT', revision: 7, ruleRevision: 3, businessDate: '2026-08-11',
  exportProfileId: 'profile-huakang-b-v1', exportProfileRevision: 2,
  exportProfileFamily: 'huakang_b_daily_plan', exportRendererCode: 'huakang_b_daily_plan_v1',
  exportBindingSource: 'IMPORT_PROFILE', calculationVersion: 'calculation-v2',
}

const metric = (value: number, unit: string, formula: string) => ({ value, numerator: value, denominator: 10, unit, sampleCount: 10, formula })
const analytics: Phase5AnalyticsRecord = {
  factoryId: 'huakang-b', dateFrom: '2026-08-01', dateTo: '2026-08-11', generatedAt: '2026-08-11T08:00:00+08:00',
  planAccuracy: metric(90, '%', 'completed / planned'), moldChangeCount: metric(8, '次', 'raw-mold-change-formula'),
  overdueRate: metric(5, '%', 'overdue / due'), machineUtilization: metric(75, '%', 'running / available'),
  integrationStatuses: [{ sourceType: 'ERP', sourceKey: 'default', cursor: 'cursor-17', status: 'ACTIVE', lastReceivedAt: '', lastSuccessAt: '2026-08-11T08:00:00+08:00', lastError: '', eventCount: 17, revision: 4 }],
  speedModels: [{ id: 'speed-1', factoryId: 'huakang-b', moldId: 'mold-1', moldNo: 'M-01', sampleCount: 8, calibratedCycleSeconds: 40, unitsPerCycle: 2, calibratedUnitsPerHour: 180, confidence: 0.82, status: 'ACTIVE', sourceWindowStart: '', sourceWindowEnd: '', lastObservedAt: '', revision: 2, updatedAt: '' }],
  deviceInterfaceConfigured: true, notes: [],
}

describe('B4d auxiliary workflow presentation runtime', () => {
  it('maps auxiliary codes with safe unknown fallbacks while retaining the raw code', () => {
    expect(label('importRowResolutionMeta', 'READY')).toMatchObject({ code: 'READY', label: '可以导入' })
    expect(label('profileStatusMeta', 'PROFILE_DRAFT').label).toBe('模板草案')
    expect(label('masterDataEntityMeta', 'COMMERCIAL_RATE_RULE').label).toBe('人民币单价规则')
    expect(label('exportBindingSourceMeta', 'LEGACY_UNKNOWN').label).toBe('历史来源，未记录模板')
    expect(label('integrationStatusMeta', 'FUTURE_STATUS')).toMatchObject({ code: 'FUTURE_STATUS', cssToken: 'unknown' })
  })

  it('keeps export diagnostics collapsed while showing business snapshot wording', () => {
    const wrapper = mount(InjectionSchedulingExportDialog, {
      props: { open: true, factoryId: 'huakang-b', plan, canExport: true, sourceMode: 'live', pendingCount: 0 },
    })
    expect(wrapper.get('.snapshot').text()).toContain('排产草案')
    expect(wrapper.get('.snapshot').text()).not.toContain('DRAFT')
    expect(wrapper.get('.snapshot').text()).not.toContain('huakang_b_daily_plan')
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.get('details').text()).toContain('IMPORT_PROFILE')
    expect(wrapper.get('details').text()).toContain('profile-huakang-b-v1')
  })

  it('renders eligibility and operations states as business labels', () => {
    const machine: MachineRecord = { id: 'machine-1', factoryId: 'huakang-b', code: 'B-01', position: '1', area: 'B', aClass: 10, aClassRaw: '10A', clampingForceTons: null, injectionCapacityG: 500, tieBarXmm: null, tieBarYmm: null, processTags: [], armCapabilities: ['single'], fixtureCapabilities: ['fixture'], processRestrictions: [], equipmentDetails: {}, remarks: '', machineType: 'standard', specialMachineType: '', status: 'available', normalizationStatus: 'COMPLETE', revision: 1 }
    const mold: MoldRecord = { id: 'mold-1', moldNo: 'M-01', name: '产品', aClass: 8, aClassRaw: '8A', netWeightG: 400, grossWeightG: 420, requiredArmType: 'single', requiredFixtureType: 'fixture', materialCode: '', materialName: '', colorProfile: '', processRequirements: [], specialMachineType: '', normalizationStatus: 'COMPLETE' }
    const eligibility = mount(EligibilityChecks, { props: { machine, mold } })
    expect(eligibility.text()).toContain('适配通过')
    expect(eligibility.text()).not.toContain('PASS')

    const dashboard = mount(Phase5OperationsDashboard, { props: { analytics, loading: false, error: '', canManageRules: true } })
    expect(dashboard.get('.integration-panel article > div').text()).toContain('正常接收')
    expect(dashboard.get('.integration-panel article > div').text()).not.toContain('default')
    expect(dashboard.get('.integration-panel article details').text()).toContain('default')
    expect(dashboard.get('.speed-model-panel article').text()).toContain('已启用')
    expect(dashboard.findAll('details').every((item) => item.attributes('open') === undefined)).toBe(true)
  })
})

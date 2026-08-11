import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import SchedulingCommandBar from '../components/SchedulingCommandBar.vue'
import SchedulingTechnicalDetails from '../components/SchedulingTechnicalDetails.vue'
import {
  assignmentDecisionMeta,
  autoScheduleRunStatusMeta,
  capacitySourceMeta,
  fitDecisionMeta,
  factoryReadinessStatusMeta,
  machineStatusMeta,
  moldEnrichmentStatusMeta,
  normalizationStatusMeta,
  planStatusMeta,
  solverStatusMeta,
  solverTypeMeta,
  taskStatusMeta,
} from '../presentation/schedulingLabels'
import { conflictFieldValue, formatConflictMessage, formatConflictTitle, formatPlanRevision } from '../presentation/schedulingFormatters'
import { planTechnicalDetails } from '../presentation/technicalDetails'

describe('injection scheduling presentation boundary', () => {
  it('maps the closed business-state catalogs without changing their raw codes or stable tokens', () => {
    expect(planStatusMeta('DRAFT')).toMatchObject({ code: 'DRAFT', label: '排产草案', cssToken: 'draft' })
    expect(planStatusMeta('PUBLISHED')).toMatchObject({ code: 'PUBLISHED', label: '当前执行', cssToken: 'published' })
    expect(taskStatusMeta('RUNNING').label).toBe('正在生产')
    expect(taskStatusMeta('CANCELLED').label).toBe('已取消')
    expect(fitDecisionMeta('REVIEW_REQUIRED').label).toBe('需要人工复核')
    expect(machineStatusMeta('maintenance').label).toBe('维护中')
    expect(normalizationStatusMeta('COMPLETE').label).toBe('资料已规范')
    expect(moldEnrichmentStatusMeta('MATCHED').label).toBe('共享资料已补齐')
    expect(factoryReadinessStatusMeta('FACTORY_READY').label).toBe('可直接排机')
    expect(autoScheduleRunStatusMeta('PARTIAL').label).toBe('方案已生成，仍有待复核或未安排项')
    expect(solverTypeMeta('CP_SAT')).toMatchObject({ code: 'CP_SAT', label: '优化求解', cssToken: 'cp-sat' })
    expect(solverStatusMeta('OPTIMAL').label).toBe('模型目标下已找到最优结果')
    expect(assignmentDecisionMeta('UNASSIGNED').label).toBe('未安排')
    expect(capacitySourceMeta('SOURCE_DAILY_CAPACITY').label).toBe('下单表模具日产量')
  })

  it('uses a safe main-surface fallback while retaining an unknown raw code for technical details', () => {
    expect(planStatusMeta('FUTURE_PLAN_STATE')).toMatchObject({
      code: 'FUTURE_PLAN_STATE',
      label: '未知状态',
      cssToken: 'unknown',
    })
    expect(capacitySourceMeta('FUTURE_CAPACITY_SOURCE')).toMatchObject({
      code: 'FUTURE_CAPACITY_SOURCE',
      label: '工时依据待确认',
      cssToken: 'unknown',
    })
    expect(moldEnrichmentStatusMeta('FUTURE_MOLD_STATE').label).toBe('共享模具状态待确认')
  })

  it('formats revisions as business versions and keeps raw plan diagnostics in collapsed technical details', () => {
    expect(formatPlanRevision(14)).toBe('版本 14')
    const items = planTechnicalDetails({
      plan: { id: 'plan-1', status: 'PUBLISHED', revision: 14, ruleRevision: 3, businessDate: '2026-08-10' },
      activeSlice: 'execution',
      eventSequence: 98,
    })
    expect(items).toContainEqual({ label: '计划原始状态', rawValue: 'PUBLISHED', copyable: false })
    expect(items).toContainEqual({ label: '事件序列', rawValue: '98', copyable: false })

    const wrapper = mount(SchedulingTechnicalDetails, { props: { items } })
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.get('summary').text()).toBe('技术信息')
    expect(wrapper.get('dl').text()).toContain('PUBLISHED')
  })

  it('turns raw revision-conflict copy into business wording', () => {
    expect(formatConflictTitle('Task revision conflict')).toBe('检测到版本冲突')
    expect(formatConflictMessage('expected revision 3 but found revision 4')).toBe('服务器数据已更新，请比较差异后采用服务器值，或基于最新版本重新应用。')
    expect(conflictFieldValue('status', 'RUNNING')).toBe('正在生产')
    expect(conflictFieldValue('status', 'QUEUED')).toBe('排队中')
  })

  it('shows a business plan label in the command bar while retaining the raw plan prop', () => {
    const wrapper = mount(SchedulingCommandBar, {
      global: {
        plugins: [createPinia()],
        stubs: { AccountMenu: { template: '<button aria-label="账号设置">账号</button>' } },
      },
      props: {
        factoryId: 'huaxing', factoryName: '华兴', sourceMode: 'live', sourceMessage: '正式数据库', syncHealth: 'live',
        refreshing: false, search: '', lastSyncedAt: '', planStatus: 'PUBLISHED', pendingCount: 0, saving: false,
        canSave: false, canImport: false, canExport: false, hasPlanningDraft: false, canPublish: false,
        publishingPlan: false, publishDisabledReason: '', saveMessage: '',
      },
    })

    expect(wrapper.text()).toContain('华兴 · 当前执行')
    expect(wrapper.text()).not.toContain('PUBLISHED')
    expect(wrapper.props('planStatus')).toBe('PUBLISHED')
  })
})

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import InjectionSchedulingExportDialog from '../components/InjectionSchedulingExportDialog.vue'
import type { SchedulingPlanRecord } from '../types'

const root = join(process.cwd(), 'src/features/injection-scheduling-v2')
const apiSource = readFileSync(join(root, 'api/injectionSchedulingV2Api.ts'), 'utf8')
const viewSource = readFileSync(join(root, 'InjectionSchedulingV2View.vue'), 'utf8')

const sourceBoundPlan: SchedulingPlanRecord = {
  id: 'plan-1', status: 'DRAFT', revision: 3, ruleRevision: 2, businessDate: '2026-08-07',
  exportProfileId: 'isprofile-huaxing-daily-v1', exportProfileRevision: 1,
  exportProfileFamily: 'huaxing_daily_plan', exportRendererCode: 'huaxing_daily_plan_v1',
  exportBindingSource: 'IMPORT_PROFILE', calculationVersion: 'injection-scheduling-calculation-v2',
}

describe('注塑排产公共计划 Phase 5 导出', () => {
  it('显式展示来源兼容与系统标准两种契约及锁定快照', () => {
    const wrapper = mount(InjectionSchedulingExportDialog, {
      props: { open: true, factoryId: 'huaxing', plan: sourceBoundPlan, canExport: true, sourceMode: 'live', pendingCount: 0 },
    })
    expect(wrapper.text()).toContain('来源兼容格式')
    expect(wrapper.text()).toContain('系统标准格式')
    expect(wrapper.get('.snapshot').text()).toContain('排产草案 · 版本 3')
    expect(wrapper.get('.snapshot').text()).toContain('来源模板已锁定')
    expect(wrapper.get('.snapshot').text()).not.toContain('DRAFT')
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.get('details').text()).toContain('isprofile-huaxing-daily-v1')
    expect(wrapper.get('details').text()).toContain('injection-scheduling-calculation-v2')
    expect(wrapper.get('button.export-primary').attributes('disabled')).toBeUndefined()
  })

  it('无来源 Profile 或有未保存修改时阻止不安全导出', async () => {
    const wrapper = mount(InjectionSchedulingExportDialog, {
      props: {
        open: true, factoryId: 'huaxing', canExport: true, sourceMode: 'live', pendingCount: 2,
        plan: { ...sourceBoundPlan, exportProfileId: null, exportProfileRevision: null, exportBindingSource: 'SYSTEM_STANDARD' },
      },
    })
    expect(wrapper.text()).toContain('当前计划未绑定可回写的来源模板')
    expect(wrapper.text()).toContain('存在 2 项未保存修改')
    expect(wrapper.get('input[value="SOURCE_COMPATIBLE"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button.export-primary').attributes('disabled')).toBeDefined()
  })

  it('API 使用 Blob 下载、显式模式与计划 Profile revision', () => {
    expect(apiSource).toContain("export_mode: mode")
    expect(apiSource).toContain('profile_id: plan.exportProfileId')
    expect(apiSource).toContain("responseType: 'blob'")
    expect(viewSource).toContain('InjectionSchedulingExportDialog')
    expect(viewSource).not.toContain('阶段 5 正在接入')
  })
})

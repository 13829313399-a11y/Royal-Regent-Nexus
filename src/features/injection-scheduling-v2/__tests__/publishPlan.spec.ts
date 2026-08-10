import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PublishPlanDialog from '../components/PublishPlanDialog.vue'
import type { SchedulingPlanRecord } from '../types'

const root = join(process.cwd(), 'src/features/injection-scheduling-v2')
const apiSource = readFileSync(join(root, 'api/injectionSchedulingV2Api.ts'), 'utf8')
const storeSource = readFileSync(join(root, 'stores/useInjectionSchedulingV2Store.ts'), 'utf8')
const commandBarSource = readFileSync(join(root, 'components/SchedulingCommandBar.vue'), 'utf8')

const plan: SchedulingPlanRecord = {
  id: 'plan-1', status: 'DRAFT', revision: 11, ruleRevision: 1, businessDate: '2026-08-10',
}

describe('计划发布入口', () => {
  it('向有排产权限的文员显示发布确认并提交', async () => {
    const wrapper = mount(PublishPlanDialog, {
      global: { stubs: { Teleport: true } },
      props: { open: true, plan, taskCount: 13, canPublish: true, publishing: false, error: '' },
    })
    expect(wrapper.text()).toContain('发布正式执行计划')
    expect(wrapper.text()).toContain('13 条任务')
    expect(wrapper.text()).toContain('自动绑定默认实体模具')
    expect(wrapper.text()).not.toContain('主管发布')
    const confirm = wrapper.findAll('button').find((item) => item.text().includes('确认发布 r11'))!
    expect(confirm.attributes('disabled')).toBeUndefined()
    await confirm.trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('调用正式发布接口，并允许排产编辑权限触发发布入口', () => {
    expect(apiSource).toContain('/injection-scheduling/plans/${plan.id}/publish')
    expect(storeSource).toContain("hasScopedPermission('injection_scheduling:edit') || hasScopedPermission('injection_scheduling:publish')")
    expect(commandBarSource).toContain('发布计划')
    expect(commandBarSource).toContain("emit('publish')")
  })
})

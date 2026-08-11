// @ts-expect-error Vitest executes this source-contract test in Node without exposing Node globals to application types.
import { readFileSync } from 'node:fs'
// @ts-expect-error Vitest executes this source-contract test in Node without exposing Node globals to application types.
import { join } from 'node:path'
import { createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SchedulingCommandBar from '../components/SchedulingCommandBar.vue'

declare const process: { cwd: () => string }
const root = join(process.cwd(), 'src/features/injection-scheduling-v2')

function mountCommandBar(overrides: Record<string, unknown> = {}) {
  return mount(SchedulingCommandBar, {
    global: {
      plugins: [createPinia()],
      stubs: { AccountMenu: { template: '<button aria-label="账号与头像设置">账号</button>' } },
    },
    props: {
      factoryId: 'huaxing',
      factoryName: '华兴',
      sourceMode: 'live',
      sourceMessage: '正式数据库',
      syncHealth: 'live',
      refreshing: false,
      search: '',
      lastSyncedAt: '09:30',
      planStatus: 'PUBLISHED',
      pendingCount: 0,
      saving: false,
      canSave: true,
      canImport: true,
      canExport: true,
      hasPlanningDraft: false,
      canPublish: false,
      publishingPlan: false,
      publishDisabledReason: '',
      saveMessage: '',
      ...overrides,
    },
  })
}

describe('B3 command bar and responsive contract', () => {
  it('uses context, search/status and action zones with one global search', async () => {
    const wrapper = mountCommandBar()

    expect(wrapper.get('[data-command-zone="context"]')).toBeTruthy()
    expect(wrapper.get('[data-command-zone="search"]')).toBeTruthy()
    expect(wrapper.get('[data-command-zone="actions"]')).toBeTruthy()
    expect(wrapper.findAll('input[type="search"]')).toHaveLength(1)
    expect(wrapper.get('input[type="search"]').attributes('aria-label')).toBe('全局搜索排产任务')

    await wrapper.get('input[type="search"]').setValue('QA-M001')
    expect(wrapper.emitted('update:search')).toEqual([['QA-M001']])
  })

  it('selects the primary action from existing sync, draft, edit and permission state', async () => {
    const stale = mountCommandBar({ syncHealth: 'stale' })
    expect(stale.get('[data-testid="command-primary-action"]').text()).toContain('重新同步')
    await stale.get('[data-testid="command-primary-action"]').trigger('click')
    expect(stale.emitted('refresh')).toHaveLength(1)

    const demo = mountCommandBar({ sourceMode: 'fallback', syncHealth: 'demo-readonly' })
    expect(demo.get('[data-testid="command-primary-action"]').attributes('disabled')).toBeDefined()
    expect(demo.get('[data-testid="command-primary-reason"]').text()).toContain('只读演示')

    const pending = mountCommandBar({ pendingCount: 3 })
    expect(pending.get('[data-testid="command-primary-action"]').text()).toContain('保存 3')
    await pending.get('[data-testid="command-primary-action"]').trigger('click')
    expect(pending.emitted('save')).toHaveLength(1)

    const draft = mountCommandBar({ planStatus: 'DRAFT', hasPlanningDraft: true, canPublish: true })
    expect(draft.get('[data-testid="command-primary-action"]').text()).toContain('发布为当前执行')
    await draft.get('[data-testid="command-primary-action"]').trigger('click')
    expect(draft.emitted('publish')).toHaveLength(1)

    const blockedDraft = mountCommandBar({ planStatus: 'DRAFT', hasPlanningDraft: true, canPublish: true, publishDisabledReason: '请先处理版本冲突' })
    expect(blockedDraft.get('[data-testid="command-primary-action"]').attributes('aria-describedby')).toBe('command-primary-reason')
    expect(blockedDraft.get('[data-testid="command-primary-reason"]').text()).toBe('请先处理版本冲突')

    const execution = mountCommandBar()
    expect(execution.get('[data-testid="command-primary-action"]').text()).toContain('自动排期')
    await execution.get('[data-testid="command-primary-action"]').trigger('click')
    expect(execution.emitted('openAutoSchedule')).toHaveLength(1)
  })

  it('keeps low-frequency operations in More while retaining their original emits', async () => {
    const wrapper = mountCommandBar()
    const menu = wrapper.get('[data-testid="command-more-menu"]')
    expect(menu.text()).toContain('刷新同步')
    expect(menu.text()).toContain('导入计划 / 下单表')
    expect(menu.text()).toContain('导出计划表')
    expect(menu.text()).toContain('共享模具库')

    await menu.get('[data-command-action="refresh"]').trigger('click')
    await menu.get('[data-command-action="import"]').trigger('click')
    await menu.get('[data-command-action="export"]').trigger('click')
    await menu.get('[data-command-action="master-data"]').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.emitted('openImport')).toHaveLength(1)
    expect(wrapper.emitted('openExport')).toHaveLength(1)
    expect(wrapper.emitted('openMasterData')).toHaveLength(1)
  })

  it('removes the duplicate plan search and keeps the global search visible at narrow widths', () => {
    const viewSource = readFileSync(join(root, 'InjectionSchedulingV2View.vue'), 'utf8')
    const polishSource = readFileSync(join(root, 'styles/polish.css'), 'utf8')
    const baseSource = readFileSync(join(root, 'injection-scheduling-v2.css'), 'utf8')

    expect(viewSource).not.toContain('class="toolbar-search"')
    expect(polishSource).not.toMatch(/command-search\s*\{\s*display:\s*none/)
    expect(polishSource).toContain('@media (max-width: 1535.98px)')
    expect(baseSource).toContain('min-width: 1024px')
  })
})

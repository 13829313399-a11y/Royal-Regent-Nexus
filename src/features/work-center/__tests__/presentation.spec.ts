import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import WorkEntryRow from '../WorkEntryRow.vue'
import WorkEntryDetail from '../WorkEntryDetail.vue'
import WorkCenterHealth from '../WorkCenterHealth.vue'
import { workHealth } from '../health'
import { entryRoute } from '../routes'
import type { WorkEntry, WorkSnapshot } from '../types'

vi.mock('@/api/workCenter', () => ({ workCenterApi: { events: vi.fn().mockResolvedValue({ items: [], next_cursor: null }) } }))
const entry: WorkEntry = {
  id: 'account_requests:registration-opaque-id:registration:1', kind: 'task', module: 'account_requests', title: '审核注册申请',
  reference_label: '张三（zhangsan）', summary: '申请岗位：工程技术员；请核对申请组织与任职资料。',
  details: [{ label: '联系电话', value: '13800000000' }, { label: '申请时间', value: '2026-09-29T01:30:00Z', format: 'datetime' }],
  lifecycle: 'open', viewer_relation: 'candidate', source_factory: { id: 'huaxing', label: '华兴' }, execution_factory: null,
  department_label: '工程部', stage_label: '审核注册申请', responsible_label: '团队队列', why_me: '你具备当前责任范围的办理权限',
  priority: 'normal', priority_reasons: [], due_at: null, due_source: null, opened_at: '2026-09-29T01:30:00Z', can_act_now: true,
  unavailable_reason: null, verification_state: 'verified', resolution_reason: null, content_version: 1, attention_version: 1,
  personal: { read_state: 'read', snoozed_until: null, archived_at: null, pinned: false, state_version: 0 },
  actions: [{ key: 'open', label: '审核注册申请', mode: 'navigate', enabled: true, disabled_reason: null,
    target: { route_key: 'account_requests', params: { id: 'registration-opaque-id' }, query: { stage: 'registration', factory: 'huaxing' } } }],
}
function snapshot(): WorkSnapshot {
  return {
    context: { viewer_key: 'qa', scope_key: 'authorized', server_time: '2026-09-29T02:00:00Z', business_timezone: 'Asia/Shanghai', authz_recheck_at: null },
    summary: { actionable_total: 1, assigned_total: 0, team_queue_total: 1, focus_total: 1, snoozed_total: 0, overdue_total: 0, info_unread_total: 0, waiting_total: 0, verification_required_total: 2 },
    query: { filtered_total: 1, cursor: null }, items: [entry], next_cursor: null, selected_entry_state: null,
    health: { status: 'partial', as_of: '2026-09-29T02:00:00Z', unavailable_sources: [], coverage: [], issues: [{ module: 'internal_quote', reason: 'source_missing', count: 2 }] },
  }
}
beforeEach(() => setActivePinia(createPinia()))

describe('readable account request previews', () => {
  it('shows applicant, summary and submission time without exposing internal IDs in the row', async () => {
    const wrapper = mount(WorkEntryRow, { props: { entry } })
    expect(wrapper.text()).toContain('张三（zhangsan）')
    expect(wrapper.text()).toContain('工程技术员')
    expect(wrapper.text()).toContain('2026-09-29 09:30 提交')
    expect(wrapper.text()).not.toContain('registration-opaque-id')
    await wrapper.trigger('click')
    expect(wrapper.emitted('select')).toEqual([[entry.id]])
  })
  it('puts readable request details before responsibility explanation and formats business time', async () => {
    const wrapper = mount(WorkEntryDetail, { props: { entry }, global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('13800000000')
    expect(text).toContain('2026-09-29 09:30')
    expect(text.indexOf('申请详情')).toBeLessThan(text.indexOf('为什么需要我'))
    expect(text).not.toContain('registration-opaque-id')
  })
  it.each(['*', 'group-management', 'group'])('opens global account requests from organization %s', factory => {
    const value = structuredClone(entry)
    value.actions[0]!.target!.query = { factory, stage: 'password_reset' }
    expect(entryRoute(value)).toEqual({ name: 'system-registration', query: { tab: 'password-reset', request_id: 'registration-opaque-id' } })
    value.actions[0]!.target!.route_key = 'shipment'
    expect(entryRoute(value)).toBeNull()
  })
  it('still rejects unsafe account identifiers', () => {
    const value = structuredClone(entry)
    value.actions[0]!.target!.params.id = '../outside'
    expect(entryRoute(value)).toBeNull()
  })
})

describe('source health explanations', () => {
  it('explains orphan notices without suggesting current synchronization is broken', () => {
    const data = snapshot()
    expect(workHealth(data)?.warning).toBe(false)
    const wrapper = mount(WorkCenterHealth, { props: { snapshot: data } })
    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.text()).toContain('当前待办已同步 · 2 条历史提醒待核对')
    expect(wrapper.text()).toContain('内部报价：2 条历史提醒未找到原单据')
    expect(wrapper.find('button').exists()).toBe(false)
  })
  it('names unavailable sources, keeps the real warning and retries', async () => {
    const data = snapshot()
    data.health.unavailable_sources = ['carton_supplier']
    const wrapper = mount(WorkCenterHealth, { props: { snapshot: data } })
    expect(wrapper.attributes('role')).toBe('alert')
    expect(wrapper.text()).toContain('供应商送货暂时无法同步')
    expect(wrapper.text()).toContain('当前计数可能不完整')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
    await wrapper.setProps({ syncing: true })
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  })
  it('does not soften stale data or invalid business state into a historical notice', () => {
    const stale = snapshot(); stale.health.status = 'stale'
    expect(workHealth(stale)).toMatchObject({ warning: true, title: '同步未完成，当前显示上次结果' })
    const invalid = snapshot(); invalid.health.issues!.push({ module: 'internal_quote', reason: 'source_inconsistent', count: 1 })
    invalid.summary.verification_required_total = 3
    expect(workHealth(invalid)).toMatchObject({ warning: true, title: '1 项业务状态需要核对' })
  })
  it('preserves a conservative warning with an older API, and removes notices after recovery', () => {
    const data = snapshot(); delete data.health.issues
    expect(workHealth(data)?.warning).toBe(true)
    data.health.status = 'fresh'
    expect(workHealth(data)).toBeNull()
  })
})

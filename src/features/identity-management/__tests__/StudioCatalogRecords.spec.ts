import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import IamRoleTemplatesView from '@/views/IamRoleTemplatesView.vue'
import StudioTimeline from '../studio/StudioTimeline.vue'

enableAutoUnmount(afterEach)
const mocks = vi.hoisted(() => ({
  roles: vi.fn(), permissions: vi.fn(), access: vi.fn(), get: vi.fn(), tasks: vi.fn(), events: vi.fn(), can: vi.fn(),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: { id: 'admin' }, can: mocks.can }) }))
vi.mock('@/api/iam', () => ({ iamApi: { listRoles: mocks.roles, listPermissions: mocks.permissions, getRoleAccess: mocks.access } }))
vi.mock('@/api/iamWorkspace', () => ({ iamWorkspaceApi: { tasks: mocks.tasks } }))
vi.mock('@/api/iam-audit', () => ({ getAuditEvents: mocks.events }))
vi.mock('@/lib/http', async original => ({ ...await original<object>(), http: { get: mocks.get } }))
vi.mock('@/components/iam/workspace/iam-navigation', async original => ({
  ...await original<object>(), iamStudioEnabled: true, consolidatedIamEnabled: true,
}))
const first = { id: 'engineer', name: '工程师', code: 'engineer', scope_mode: 'own_factory', description: '工程部基础包',
  is_system_position: true, position_department: 'engineering', position_department_name: '工程部', position_sort_order: 1,
  permission_count: 1, scoped_member_count: 1, scoped_binding_count: 2, definition_version: 'v1' }
const second = { ...first, id: 'manager', name: '工程经理', permission_count: 2, scoped_member_count: null, position_sort_order: 2 }
const read = { code: 'orders:read', name: '查看订单', module_name: '订单', module_code: 'orders', access_kind: 'read', risk_level: 'normal', status: 'active', sort_order: 1 }
const highRisk = { ...read, code: 'system:approve', name: '审批', module_name: '系统管理', module_code: 'system', access_kind: 'operate', risk_level: 'high', sort_order: 2 }
beforeEach(() => {
  vi.resetAllMocks()
  mocks.can.mockReturnValue(true)
  mocks.roles.mockResolvedValue([first, second])
  mocks.permissions.mockResolvedValue([read, highRisk])
  mocks.access.mockImplementation(async (id: string) => id === first.id ? { ...first, permission_codes: [read.code] } : { ...second, permission_codes: [read.code, highRisk.code] })
  mocks.get.mockResolvedValue({ data: { members_restricted: false, total: 0, items: [] } })
  mocks.tasks.mockResolvedValue({ items: [], visible_total: 0, coverage: [] })
  mocks.events.mockResolvedValue([])
})
async function routerAt(path: string) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{path: '/:pathMatch(.*)*', component: {template: '<div/>'}}] })
  await router.push(path)
  await router.isReady()
  return router
}
it('reports scoped directory counts, zero-coverage modules and mutually exclusive comparison results', async () => {
  const router = await routerAt('/system/iam/roles?role=engineer')
  const page = mount(IamRoleTemplatesView, { global: { plugins: [router] } })
  await flushPromises()
  expect(page.get('.iam-directory-scroll').text()).toContain('1 人')
  expect(page.get('.iam-directory-scroll').text()).toContain('受限')
  const chip = page.get('.iam-role-coverage .uncovered')
  expect(chip.text()).toContain('0/1')
  await chip.trigger('click')
  expect(page.text()).toContain('当前筛选没有匹配的权限')
  await page.get('[aria-label="权限显示范围"]').setValue('all')
  expect(page.get('.iam-capability-row').text()).toContain('未包含')
  await page.get('select[aria-label="对比另一方案"]').setValue('manager')
  await flushPromises()
  expect(page.get('.iam-compare-common').text()).toContain('查看订单')
  expect(page.get('.iam-compare-right').text()).toContain('审批')
  expect(page.find('.iam-capability-grid').exists()).toBe(false)
  await page.get('.iam-compare-banner button').trigger('click')
  await flushPromises()
  expect(page.find('.iam-capability-grid').exists()).toBe(true)
})
it('filters fixed-role permissions by risk without exposing controls to edit the permission list', async () => {
  const router = await routerAt('/system/iam/roles?role=engineer')
  const page = mount(IamRoleTemplatesView, { global: { plugins: [router] } })
  await flushPromises()
  await page.get('[aria-label="权限显示范围"]').setValue('all')
  const list = page.get('[data-testid="role-permission-scroll-region"]')
  expect(list.findAll('.iam-capability-row')).toHaveLength(2)
  await page.get('[data-testid="permission-filter-toolbar"] input[type="checkbox"]').setValue(true)
  expect(list.findAll('.iam-capability-row')).toHaveLength(1)
  expect(list.text()).toContain('审批')
  expect(list.text()).toContain('未包含')
  expect(list.find('input, select, textarea, [contenteditable="true"], [role="checkbox"], [role="radio"], [role="switch"]').exists()).toBe(false)
})
it('reads members only with personnel access, keeping multiple visible bindings under one employee', async () => {
  const router = await routerAt('/system/iam/roles?role=engineer&tab=members')
  const binding = { binding_id: 'one', department: 'engineering', factory_id: 'huaxing', role_version_id: 'v1', version_outdated: true, factory_ceiling: null, source_type: 'assignment', assignment_id: 'assignment' }
  mocks.get.mockResolvedValue({ data: { members_restricted: false, total: 1, items: [{user_id: 'person', display_name: '员工甲', username: 'tester', primary_org_unit_id: 'huaxing', primary_department: 'engineering', position: '工程师',
    bindings: [binding, {...binding, binding_id: 'two', version_outdated: false, factory_ceiling: []}]}] } })
  const page = mount(IamRoleTemplatesView, { global: { plugins: [router] } })
  await flushPromises()
  expect(page.get('.iam-role-banner').text()).toContain('2 条可见绑定')
  expect(page.get('.iam-role-banner').text()).toContain('1 名可见成员')
  expect(page.findAll('tbody tr')).toHaveLength(1)
  expect(page.get('tbody tr').text()).toContain('员工甲')
  expect(page.get('tbody details').attributes('open')).toBeUndefined()
  expect(page.get('tbody summary').text()).toContain('2 条绑定来源')
  expect(page.get('tbody details a').attributes('href')).toContain('binding=one')
  expect(page.text()).toContain('无业务厂区')
  page.unmount()
  mocks.get.mockClear()
  mocks.can.mockImplementation((code: string) => code !== 'system:user_manage')
  const restricted = mount(IamRoleTemplatesView, { global: { plugins: [router] } })
  await flushPromises()
  expect(restricted.text()).toContain('成员资料受保护')
  expect(mocks.get).not.toHaveBeenCalled()
})
it('preserves the original audit values and shows only recorded changes across the two snapshots', async () => {
  mocks.events.mockResolvedValue([{ id: 'event-1', event_type: 'role_template_updated', created_at: '2026-01-02T00:00:00Z', actor_name: '审核人',
    before_value: {permission_codes: [read.code]}, after_value: {permission_codes: [highRisk.code]}, request_id: 'request-7' }])
  const router = await routerAt('/system/iam/audit')
  const page = mount(StudioTimeline, { global: { plugins: [router] } })
  await flushPromises()
  expect(page.get('.iam-audit-diff').text()).toContain('1 项权限')
  expect(page.findAll('.iam-audit-chips > span')).toHaveLength(2)
  expect(page.get('details pre').text()).toContain(read.code)
  expect(page.get('footer').text()).toContain('授权申请 request-7')
  await page.findAll('nav button').find(button => button.text() === '岗位更新')!.trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.query.type).toBe('position')
  expect(mocks.tasks).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'position' }))
  expect(page.text()).toContain('当前范围暂无可见记录')
  expect(page.find('.iam-audit-record').exists()).toBe(false)
})
it('orders a cross-day decision by the recorded decision time and keeps application time and receipt', async () => {
  mocks.tasks.mockResolvedValue({items:[{key:'position:old', kind:'position', source_id:'old', state:'closed',
    raw_status:'applied', available_actions:[], subject:{display_name:'员工甲'}, created_at:'2026-01-01T01:00:00Z',
    record_decision_at:'2026-01-12T01:00:00Z', record_receipt_id:'received-12'}], coverage:[], visible_total:1})
  mocks.events.mockResolvedValue([{id:'event', event_type:'role_template_updated', target_type:'role', target_id:'business-role',
    created_at:'2026-01-08 08:00:00', occurred_at:'2026-01-08T08:00:00+01:00',
    before_value:{state:'active'}, after_value:{state:'revoked'}}])
  const router = await routerAt('/system/iam/audit')
  const page = mount(StudioTimeline, {global:{plugins:[router]}})
  await flushPromises()
  const [task,event] = page.findAll('article')
  expect(task!.get('time').attributes('datetime')).toBe('2026-01-12T01:00:00Z')
  expect(task!.text()).toContain('申请 ·')
  expect(task!.text()).toContain('回执 received-12')
  expect(event!.get('.iam-audit-diff').text()).toContain('已撤销')
  expect(event!.text()).toContain('权限方案 · business-role')
  expect(event!.get('time').attributes('datetime')).toBe('2026-01-08T08:00:00+01:00')
  expect(mocks.tasks).toHaveBeenCalledWith(expect.objectContaining({sort:'activity'}))
})

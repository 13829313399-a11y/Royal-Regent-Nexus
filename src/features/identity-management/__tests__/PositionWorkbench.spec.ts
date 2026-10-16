import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import PositionWorkbench from '../PositionWorkbench.vue'
import { reactive } from 'vue'
import { consolidatedIamTarget } from '@/router/iamCompatibility'

const mocks = vi.hoisted(() => ({
  people: vi.fn(), person: vi.fn(), adjust: vi.fn(), catalog: vi.fn(), queue: vi.fn(), tasks: vi.fn(), updateUserStatus: vi.fn(),
  permissions: ['system:user_manage', 'system:access_manage', 'system:permission_catalog_read', 'system:audit_read'],
  auth: { currentUser: { id: 'admin', identity: { employment_epoch: 1, effective_context_key: 'initial' } }, authorizationVersion: 1 },
}))
vi.mock('@/stores/auth', async () => {
  const { reactive } = await import('vue')
  const auth = reactive(mocks.auth)
  return { useAuthStore: () => ({ get currentUser() { return auth.currentUser }, get authorizationVersion() { return auth.authorizationVersion },
    can: (permission: string) => mocks.permissions.includes(permission) }) }
})
vi.mock('@/views/UserAccessManagementView.vue', () => ({ __esModule: true, default: { props: ['targetUserId'], template: '<div>最小个人例外：{{ targetUserId }}</div>' } }))
vi.mock('@/api/identity', async (original) => ({ ...(await original<object>()), identityApi: mocks }))
vi.mock('@/api/iamWorkspace', () => ({ iamWorkspaceApi: mocks }))
vi.mock('@/api/system', () => ({ systemApi: mocks }))
vi.mock('@/api/positionReviews', () => ({ positionReviewsApi: mocks, positionStatus: {} }))
const person = { id: 'p', display_name: '只读人员甲', username: 'person-a', position: '工程师',
  primary_factory_id: 'huakang-a', primary_department: 'engineering', identity_mode: 'v2',
  employment_status: 'active', identity_version: 1, status: 'active' }
beforeEach(() => {
  vi.clearAllMocks()
  mocks.catalog.mockResolvedValue({ organizations: [], writes_enabled: true })
  mocks.people.mockResolvedValue({ items: [person], total: 1 })
  mocks.person.mockResolvedValue({ ...person, assignments: [], role_bindings: [], overrides: [], primary_assignment: null })
  mocks.queue.mockResolvedValue({ items: [], total: 0, actionable_total: 0 })
  mocks.tasks.mockResolvedValue({ items: [], visible_total: 0, actionable_total: 0, coverage: [], partial: false })
  mocks.adjust.mockResolvedValue({ item_key: 'position:new', reused: false })
  mocks.updateUserStatus.mockResolvedValue({})
  mocks.permissions = ['system:user_manage', 'system:access_manage', 'system:permission_catalog_read', 'system:audit_read']
  reactive(mocks.auth).currentUser.id = 'admin'
  reactive(mocks.auth).authorizationVersion = 1
})
it('access-only deep links mount exceptions without fetching the people list or identity', async () => {
  mocks.permissions = ['system:access_manage']
  const { wrapper } = await setup('/system/users?view=people&person=p&panel=exceptions')
  expect(mocks.people).not.toHaveBeenCalled()
  expect(mocks.person).not.toHaveBeenCalled()
  expect(mocks.adjust).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('最小个人例外：p')
  wrapper.unmount()
})
it('late person A cannot overwrite selected person B', async () => {
  let finish!: (value: unknown) => void
  mocks.person.mockImplementation((id: string) => id === 'a' ? new Promise(resolve => { finish = resolve }) : Promise.resolve({ ...person, id: 'b', display_name: '人员乙', assignments: [], role_bindings: [], overrides: [] }))
  const { wrapper, router } = await setup('/system/users?person=a')
  await router.replace('/system/users?person=b'); await flushPromises()
  finish({ ...person, id: 'a', display_name: '迟到甲', assignments: [], role_bindings: [], overrides: [] }); await flushPromises()
  expect(wrapper.text()).toContain('人员乙'); expect(wrapper.text()).not.toContain('迟到甲')
  expect(mocks.adjust).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('clears protected person data synchronously when the viewer changes', async () => {
  const { wrapper } = await setup('/system/users?person=p')
  mocks.person.mockReturnValue(new Promise(() => {})); mocks.people.mockReturnValue(new Promise(() => {}))
  reactive(mocks.auth).currentUser.id = 'another-viewer'
  await flushPromises()
  expect(wrapper.text()).not.toContain('只读人员甲')
  wrapper.unmount()
})
async function setup(path: string) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/system/users', component: PositionWorkbench },
  ] })
  router.beforeEach(to => consolidatedIamTarget(to, true))
  await router.push(path); await router.isReady()
  const wrapper = mount(RouterView, { global: { plugins: [router], stubs: { PositionReviewPane: true, AccessExplanation: true, DelegationEditor: true, IdentityWizard: true,
    IamDialogSurface: { props: ['open', 'title', 'description'], template: '<section v-if="open" role="dialog" :aria-label="title"><p>{{ description }}</p><slot /></section>' } } } })
  await flushPromises()
  return { wrapper, router }
}
it('opens direct position and package management through the canonical router without creating a review', async () => {
  const { wrapper, router } = await setup('/system/users?person=p')
  await wrapper.findAll('button').find(b => b.text() === '调整职位与权限')!.trigger('click'); await flushPromises()
  expect(router.currentRoute.value.query).toMatchObject({ view: 'people', person: 'p', panel: 'manage' })
  expect(wrapper.get('[role=dialog]').attributes('aria-label')).toBe('调整职位与权限')
  expect(mocks.adjust).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('opening and refreshing a person deep link reads identity without starting a review', async () => {
  const { wrapper } = await setup('/system/users?person=p')
  expect(mocks.person).toHaveBeenCalledWith('p')
  expect(mocks.adjust).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('只读人员甲')
  wrapper.unmount()
})
it('does not present ended or scheduled appointment packages as current authorization after a transfer', async () => {
  mocks.person.mockResolvedValue({ ...person, employment_epoch: 1, server_now: '2026-10-15T08:00:00Z',
    assignments: [{ id: 'old', state: 'ended' }, { id: 'current', state: 'current' }, { id: 'future', state: 'scheduled' }],
    active_assignments_summary: [{ id: 'current' }], overrides: [],
    role_bindings: [
      { id: 'a', assignment_id: 'old', role_name: '旧岗位权限包', state: 'active' },
      { id: 'b', assignment_id: 'current', role_name: '新岗位权限包', state: 'active' },
      { id: 'c', assignment_id: 'future', role_name: '未来岗位权限包', state: 'active' },
      { id: 'd', role_name: '过期独立包', state: 'active', employment_epoch: 1, valid_until: '2026-10-14T08:00:00Z' },
    ] })
  const { wrapper } = await setup('/system/users?person=p')
  const sources = wrapper.findAll('.iw-source').map(e => e.text()).join(' ')
  expect(sources).toContain('新岗位权限包')
  expect(sources).not.toMatch(/旧岗位权限包|未来岗位权限包|过期独立包/)
  wrapper.unmount()
})
it.each([
  ['active', 'suspended', '停用账号', '确认停用', '账号已停用'],
  ['suspended', 'active', '恢复账号', '确认恢复', '账号已恢复'],
])('manages %s accounts with personnel permission even when advanced writes are disabled', async (status, desired, action, confirm, success) => {
  mocks.permissions = ['system:user_manage']
  mocks.catalog.mockResolvedValue({ organizations: [], writes_enabled: false })
  const details = { ...person, status, assignments: [], role_bindings: [], overrides: [] }
  mocks.person.mockResolvedValueOnce(details).mockResolvedValue({ ...details, status: desired })
  const { wrapper } = await setup('/system/users?person=p&panel=account')
  await wrapper.findAll('button').find(b => b.text() === action)!.trigger('click')
  expect(wrapper.get('[role=dialog]').text()).toContain('person-a')
  expect(mocks.updateUserStatus).not.toHaveBeenCalled()
  await wrapper.findAll('button').find(b => b.text() === confirm)!.trigger('click'); await flushPromises()
  expect(mocks.updateUserStatus).toHaveBeenCalledExactlyOnceWith('p', { status: desired })
  expect(wrapper.text()).toContain(success)
  expect(mocks.adjust).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('cancelling account stop has no write and unavailable account states have no toggle', async () => {
  const { wrapper, router } = await setup('/system/users?person=p')
  await wrapper.findAll('button').find(b => b.text() === '停用账号')!.trigger('click')
  await wrapper.findAll('button').find(b => b.text() === '取消')!.trigger('click')
  expect(mocks.updateUserStatus).not.toHaveBeenCalled()
  for (const status of ['pending', 'rejected', 'retired']) {
    mocks.person.mockResolvedValue({ ...person, status, assignments: [], role_bindings: [], overrides: [] })
    await router.replace(`/system/users?person=${status}`); await flushPromises()
    expect(wrapper.findAll('button').some(b => ['停用账号', '恢复账号'].includes(b.text()))).toBe(false)
    if (status === 'retired') expect(wrapper.text()).toContain('已停用')
  }
  wrapper.unmount()
})
it('keeps an unknown stop locked until the current account state confirms it', async () => {
  mocks.updateUserStatus.mockRejectedValueOnce(new Error('network lost'))
  const { wrapper, router } = await setup('/system/users?person=p')
  await wrapper.findAll('button').find(b => b.text() === '停用账号')!.trigger('click')
  await wrapper.findAll('button').find(b => b.text() === '确认停用')!.trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('账号状态提交结果待确认')
  expect(wrapper.findAll('button').find(b => b.text() === '停用账号')!.attributes('disabled')).toBeDefined()
  await router.replace('/system/users?person=another'); await flushPromises()
  expect(router.currentRoute.value.query.person).toBe('p')
  mocks.person.mockResolvedValue({ ...person, status: 'suspended', assignments: [], role_bindings: [], overrides: [] })
  await wrapper.findAll('button').find(b => b.text() === '核查账号状态')!.trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('已核实账号状态：已停用')
  expect(mocks.updateUserStatus).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})
it('keeps the account active and shows a rejected stop reason', async () => {
  mocks.updateUserStatus.mockRejectedValueOnce({ isAxiosError: true, response: { status: 400, data: { detail: '不能停用最后一个集团超级管理员' } } })
  const { wrapper } = await setup('/system/users?person=p')
  await wrapper.findAll('button').find(b => b.text() === '停用账号')!.trigger('click')
  await wrapper.findAll('button').find(b => b.text() === '确认停用')!.trigger('click'); await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('不能停用最后一个集团超级管理员')
  expect(wrapper.text()).not.toContain('账号已停用')
  wrapper.unmount()
})
it('can safely retry the same target status when a lost request never reached the server', async () => {
  mocks.updateUserStatus.mockRejectedValueOnce(new Error('request not sent')).mockResolvedValue({})
  const { wrapper } = await setup('/system/users?person=p')
  await wrapper.findAll('button').find(b => b.text() === '停用账号')!.trigger('click')
  await wrapper.findAll('button').find(b => b.text() === '确认停用')!.trigger('click'); await flushPromises()
  await wrapper.findAll('button').find(b => b.text() === '核查账号状态')!.trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('尚未观察到目标状态')
  mocks.person.mockResolvedValue({ ...person, status: 'suspended', assignments: [], role_bindings: [], overrides: [] })
  await wrapper.findAll('button').find(b => b.text() === '重试停用账号')!.trigger('click'); await flushPromises()
  expect(mocks.updateUserStatus.mock.calls).toEqual([['p', { status: 'suspended' }], ['p', { status: 'suspended' }]])
  expect(wrapper.text()).toContain('账号已停用')
  wrapper.unmount()
})
it.each(['profile', 'account'])('shows account and current profile contacts directly in the %s panel', async panel => {
  mocks.person.mockResolvedValue({ ...person, username: 'current-account', phone: '13800000000', email: 'current@example.com',
    assignments: [], role_bindings: [], overrides: [] })
  const { wrapper } = await setup(`/system/users?person=p&panel=${panel}`)
  const facts = Object.fromEntries(wrapper.findAll('.iw-facts > div').map(item => [item.get('dt').text(), item.get('dd').text()]))
  expect(facts).toMatchObject({ 登录账号: 'current-account', 手机号码: '13800000000', 邮箱: 'current@example.com' })
  expect(wrapper.get('.iw-facts').element.closest('details')).toBeNull()
  expect(mocks.adjust).not.toHaveBeenCalled()
  wrapper.unmount()
})
it.each([
  ['', '  ', '未填写'],
  [null, null, '未记录'],
  [undefined, undefined, '未记录'],
])('labels empty or unavailable personnel contacts explicitly (%s)', async (phone, email, expected) => {
  mocks.person.mockResolvedValue({ ...person, phone, email, assignments: [], role_bindings: [], overrides: [] })
  const { wrapper } = await setup('/system/users?person=p')
  const facts = Object.fromEntries(wrapper.findAll('.iw-facts > div').map(item => [item.get('dt').text(), item.get('dd').text()]))
  expect(facts).toMatchObject({ 登录账号: 'person-a', 手机号码: expected, 邮箱: expected })
  wrapper.unmount()
})
it.each([
  ['2026-10-14T02:05:09Z', '2026-10-14 10:05', '2026-10-14 10:05:09'],
  ['', '从未登录', '从未登录'],
  [undefined, '暂无记录', '暂无记录'],
  ['invalid-time', '暂无记录', '暂无记录'],
])('shows last successful login in the list and account detail (%s)', async (last_login_at, listText, detailText) => {
  mocks.people.mockResolvedValue({ items: [{ ...person, last_login_at }], total: 1 })
  mocks.person.mockResolvedValue({ ...person, last_login_at, assignments: [], role_bindings: [], overrides: [] })
  const { wrapper, router } = await setup('/system/users?view=people')
  expect(wrapper.get('.iw-table-head').text()).toContain('最近登录')
  expect(wrapper.get('.iw-last-login').text()).toBe(listText)
  await wrapper.get('.iw-person-row').trigger('click'); await flushPromises()
  await router.replace('/system/users?view=people&person=p&panel=account'); await flushPromises()
  const fact = wrapper.findAll('.iw-facts > div').find(item => item.find('dt').text() === '最近登录')!
  expect(fact.get('dd').text()).toBe(detailText)
  expect(wrapper.text()).toContain('按北京时间显示')
  expect(mocks.adjust).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('requeries search text even when filters leave the current URL unchanged', async () => {
  const { wrapper } = await setup('/system/users?view=people')
  await wrapper.get('input[type=search]').setValue('qa-engineer')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(mocks.people).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'qa-engineer', page: 1 }))
  expect(mocks.people).toHaveBeenCalledTimes(2)
  expect(mocks.adjust).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('selecting a person is read-only; only the named start action may create a review', async () => {
  const { wrapper } = await setup('/system/users?tab=people')
  const row = wrapper.findAll('button').find(b => b.text().includes('只读人员甲'))!
  await row.trigger('click'); await flushPromises()
  expect(mocks.adjust).not.toHaveBeenCalled()
  expect(mocks.person).toHaveBeenCalledWith('p')
  const start = wrapper.findAll('button').find(b => b.text().includes('按内置方案快速调整'))!
  expect(start).toBeDefined()
  await start.trigger('click'); await flushPromises()
  expect(mocks.adjust).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})

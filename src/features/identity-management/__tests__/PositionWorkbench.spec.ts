import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import PositionWorkbench from '../PositionWorkbench.vue'
import { reactive } from 'vue'

const mocks = vi.hoisted(() => ({
  people: vi.fn(), person: vi.fn(), adjust: vi.fn(), catalog: vi.fn(), queue: vi.fn(), tasks: vi.fn(),
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
  await router.push(path); await router.isReady()
  const wrapper = mount(PositionWorkbench, { global: { plugins: [router], stubs: { PositionReviewPane: true, AccessExplanation: true, DelegationEditor: true, IdentityWizard: true } } })
  await flushPromises()
  return { wrapper, router }
}
it('opening and refreshing a person deep link reads identity without starting a review', async () => {
  const { wrapper } = await setup('/system/users?person=p')
  expect(mocks.person).toHaveBeenCalledWith('p')
  expect(mocks.adjust).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('只读人员甲')
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
  const start = wrapper.findAll('button').find(b => b.text().includes('发起岗位 / 权限调整'))!
  expect(start).toBeDefined()
  await start.trigger('click'); await flushPromises()
  expect(mocks.adjust).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})

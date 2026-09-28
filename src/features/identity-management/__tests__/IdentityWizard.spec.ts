import { flushPromises, mount, enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import IdentityWizard from '../IdentityWizard.vue'
import type {
  ChangePreview,
  ChangeRecord,
  PersonIdentity,
  OrganizationCatalog,
} from '@/api/identity'
const api = vi.hoisted(() => ({
  draft: vi.fn(),
  preview: vi.fn(),
  commit: vi.fn(),
  change: vi.fn(),
}))
vi.mock('@/api/identity', async (original) => ({ ...(await original<object>()), identityApi: api }))
vi.mock('@/api/iam', () => ({ iamApi: { listRoles: async () => [] } }))
enableAutoUnmount(afterEach)
const person = {
  id: 'p',
  display_name: '测试员工',
  identity_mode: 'v2',
  employment_status: 'active',
  identity_version: 3,
  authorization_version: 5,
  primary_factory_id: 'f',
  primary_department: 'd',
  position: '工程师',
  assignments: [],
  active_assignments_summary: [],
  primary_assignment: null,
  role_bindings: [],
  overrides: [],
  handover: { count: 0, coverage: [] },
} as unknown as PersonIdentity
const catalog = {
  organizations: [
    {
      id: 'f',
      name: '测试厂',
      status: 'active',
      kind: 'factory',
      departments: [{ code: 'd', name: '工程部' }],
    },
  ],
  writes_enabled: true,
  scheduling_enabled: false,
} as OrganizationCatalog
const row = {
  id: 'draft-1',
  request_type: 'primary_assignment_transfer',
  revision: 1,
  state: 'draft',
} as ChangeRecord
const impact = (): ChangePreview => ({
  preview_token: 'token-1',
  expires_at: new Date(Date.now() + 60000).toISOString(),
  request_revision: 1,
  requires_approval: false,
  high_risk: false,
  before_identity: person,
  after_identity: person,
  effective_at: new Date().toISOString(),
  permission_diffs: { added: [], removed: [], retained: [], source_changed: [] },
  handover_summary: { count: 0, status: '', coverage: [] },
})
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((r, j) => {
    resolve = r
    reject = j
  })
  return { promise, resolve, reject }
}
const mountView = (target = person) =>
  mount(IdentityWizard, {
    props: { person: target, catalog },
    global: { stubs: { AccessImpact: { template: '<div>impact</div>' } } },
  })
const button = (wrapper: ReturnType<typeof mountView>, text: string) =>
  wrapper.findAll('button').find((b) => b.text() === text)!
beforeEach(() => {
  vi.resetAllMocks()
  api.draft.mockResolvedValue(row)
  api.preview.mockResolvedValue(impact())
  api.commit.mockResolvedValue({ ...row, state: 'applied' })
})
async function toForm(wrapper: ReturnType<typeof mountView>) {
  await button(wrapper, '下一步：填写资料').trigger('click')
  await flushPromises()
}
async function preview(wrapper: ReturnType<typeof mountView>) {
  await toForm(wrapper)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}
it('starts clean and does not save until the second step is submitted', async () => {
  const wrapper = mountView()
  await flushPromises()
  expect(wrapper.find('form').exists()).toBe(false)
  expect(api.draft).not.toHaveBeenCalled()
  expect(wrapper.emitted('dirty')).toBeUndefined()
  await toForm(wrapper)
  expect(wrapper.find('form').exists()).toBe(true)
  expect(api.draft).not.toHaveBeenCalled()
})
it('preserves the draft after preview failure and patches it on retry', async () => {
  api.preview.mockRejectedValueOnce(new Error('预览服务暂不可用'))
  const wrapper = mountView()
  await preview(wrapper)
  expect(wrapper.text()).toContain('预览服务暂不可用')
  expect(wrapper.text()).toContain('draft-1')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(api.draft.mock.calls[1]?.[1]).toEqual(row)
  expect(wrapper.text()).toContain('确认此次变更')
})
it('never revives a preview that was edited while the server was responding', async () => {
  const pending = deferred<ChangePreview>()
  api.preview.mockReturnValue(pending.promise)
  const wrapper = mountView()
  await toForm(wrapper)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  await wrapper.get('textarea').setValue('输入已更新')
  pending.resolve(impact())
  await flushPromises()
  expect(wrapper.text()).not.toContain('确认此次变更')
  expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)
  expect(api.commit).not.toHaveBeenCalled()
})
it.each(['applied', 'scheduled', 'pending_approval'])(
  'reports the actual %s result and blocks double submit',
  async (state) => {
    const pending = deferred<ChangeRecord>()
    api.commit.mockReturnValue(pending.promise)
    const wrapper = mountView()
    await preview(wrapper)
    await wrapper.get('input[type="checkbox"]').setValue(true)
    const submit = button(wrapper, '确认办理')
    await submit.trigger('click')
    await submit.trigger('click')
    expect(api.commit).toHaveBeenCalledTimes(1)
    pending.resolve({ ...row, state })
    await flushPromises()
    expect(wrapper.emitted('saved')?.[0]?.[0]).toMatchObject({ state })
  },
)
it('holds an unknown commit result until a single-record read resolves it', async () => {
  api.commit.mockRejectedValue(new Error('Network Error'))
  api.change.mockResolvedValue({ ...row, state: 'scheduled' })
  const wrapper = mountView()
  await preview(wrapper)
  await wrapper.get('input[type="checkbox"]').setValue(true)
  await button(wrapper, '确认办理').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('提交结果待核查')
  expect(button(wrapper, '确认办理').attributes('disabled')).toBeDefined()
  expect(api.draft).toHaveBeenCalledTimes(1)
  await button(wrapper, '核查提交结果').trigger('click')
  await flushPromises()
  expect(api.change).toHaveBeenCalledWith('draft-1')
  expect(wrapper.emitted('saved')?.[0]?.[0]).toMatchObject({ state: 'scheduled' })
})
it('blocks expired previews', async () => {
  api.preview.mockResolvedValue({ ...impact(), expires_at: '2000-01-01T00:00:00Z' })
  const wrapper = mountView()
  await preview(wrapper)
  expect(wrapper.text()).toContain('预览已过期')
  expect(button(wrapper, '确认办理').attributes('disabled')).toBeDefined()
  expect(api.commit).not.toHaveBeenCalled()
})
it('preserves confirmed legacy profile and sends no implicit permission packages', async () => {
  const wrapper = mountView({
    ...person,
    identity_mode: 'legacy',
    confirmation_status: 'confirmed',
  })
  await toForm(wrapper)
  expect(wrapper.get('input[maxlength="128"]').attributes('readonly')).toBeDefined()
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(api.draft.mock.calls[0]?.[0]).toMatchObject({
    request_type: 'confirm_identity',
    new_assignment: {
      org_unit_id: 'f',
      department_code: 'd',
      official_position_title: '工程师',
      role_bindings: [],
    },
  })
})

it('starts with rehire for a departed person even without clicking the only choice', async () => {
  const wrapper = mountView({ ...person, employment_status: 'left' })
  await toForm(wrapper)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(api.draft.mock.calls[0]?.[0].request_type).toBe('rehire')
})

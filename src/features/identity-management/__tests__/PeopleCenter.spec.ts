import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, reactive } from 'vue'
import { beforeEach, expect, it, vi } from 'vitest'
import PeopleCenter from '../PeopleCenter.vue'

const api = vi.hoisted(() => ({ catalog: vi.fn(), people: vi.fn(), person: vi.fn() }))
vi.mock('@/api/identity', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  identityApi: api,
}))
const routeState = reactive({ query: {} as Record<string, string> })
vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({
    push: ({ query }: { query: Record<string, string> }) => {
      routeState.query = query
    },
    replace: ({ query }: { query: Record<string, string> }) => {
      routeState.query = query
    },
  }),
  onBeforeRouteLeave: vi.fn(),
  onBeforeRouteUpdate: vi.fn(),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: { id: 'manager' } }) }))

beforeEach(() => {
  vi.resetAllMocks()
  routeState.query = {}
})

const simpleMount = () =>
  mount(PeopleCenter, {
    global: {
      stubs: {
        IdentityShell: { template: '<div><slot /></div>' },
        RouterLink: { template: '<a><slot /></a>' },
        AccessExplanation: true,
        IdentityWizard: true,
        teleport: { template: '<div><slot /></div>' },
      },
    },
  })

it('retries an initial organization-catalog failure and restores the actual catalog', async () => {
  api.catalog
    .mockRejectedValueOnce(new Error('组织目录暂不可用'))
    .mockResolvedValue({
      writes_enabled: true,
      organizations: [{ id: 'huakang-a', name: '华康A厂', kind: 'factory', departments: [] }],
    })
  api.people.mockResolvedValue({ items: [], total: 0 })
  const wrapper = simpleMount()
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('组织目录暂不可用')
  expect(wrapper.text()).not.toContain('当前管理范围没有人员')
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '重试')!
    .trigger('click')
  await flushPromises()
  expect(api.catalog).toHaveBeenCalledTimes(2)
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.text()).toContain('华康A厂')
  expect(wrapper.text()).toContain('当前管理范围没有人员')
  wrapper.unmount()
})

it.each(['无权限查看人员管理', '服务暂不可用'])(
  'distinguishes %s from empty and no-results states',
  async (message) => {
    api.catalog.mockResolvedValue({ writes_enabled: false, organizations: [] })
    api.people.mockRejectedValueOnce(new Error(message)).mockResolvedValue({ items: [], total: 0 })
    const wrapper = simpleMount()
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain(message)
    expect(wrapper.text()).not.toContain('当前管理范围没有人员')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === '重试')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('当前管理范围没有人员')
    await wrapper.get('input[aria-label="搜索姓名或账号"]').setValue('没有这个人')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('当前筛选没有匹配人员')
    wrapper.unmount()
  },
)

it('blocks the next transaction while the completed assignment is still being refreshed', async () => {
  const person = {
    id: 'person',
    display_name: '测试人员',
    username: 'test-person',
    identity_mode: 'legacy',
    identity_version: 0,
    primary_factory_id: 'huakang-a',
    primary_department: 'engineering',
    position: '工程师',
    status: 'active',
    active_assignments_summary: [],
    assignments: [],
    role_bindings: [],
    overrides: [],
    handover: { count: 0, coverage: [] },
  }
  api.catalog.mockResolvedValue({ writes_enabled: true, organizations: [] })
  api.people.mockResolvedValue({ items: [person], total: 1 })
  api.person.mockResolvedValueOnce(person)
  const previousShowModal = Object.getOwnPropertyDescriptor(
    HTMLDialogElement.prototype,
    'showModal',
  )
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.open = true
    },
  })
  const wrapper = mount(PeopleCenter, {
    global: {
      stubs: {
        teleport: { template: '<div><slot /></div>' },
        IdentityShell: { template: '<div><slot /></div>' },
        RouterLink: { template: '<a><slot /></a>' },
        AccessExplanation: true,
        IdentityWizard: defineComponent({
          props: ['person'],
          emits: ['saved'],
          template:
            '<button @click="$emit(\'saved\')">测试办结 {{ person.identity_version }}</button>',
        }),
      },
    },
  })
  await flushPromises()
  await wrapper.get('.iam-person-row').trigger('click')
  await flushPromises()
  const action = () => wrapper.get('.iam-actions button')
  await action().trigger('click')
  let resolve!: (value: typeof person) => void
  api.person.mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  await wrapper
    .findAll('button')
    .find((b) => b.text().startsWith('测试办结'))!
    .trigger('click')
  expect(action().attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain('正在刷新任职')
  expect(wrapper.text()).not.toContain('测试办结')
  resolve({ ...person, identity_mode: 'v2', identity_version: 1 })
  await flushPromises()
  expect(action().attributes('disabled')).toBeUndefined()
  await action().trigger('click')
  expect(wrapper.text()).toContain('测试办结 1')
  wrapper.unmount()
  if (previousShowModal)
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', previousShowModal)
  else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
  vi.restoreAllMocks()
})

function delayed<T>() {
  let resolve!: (value: T) => void
  let reject!: (value: Error) => void
  const promise = new Promise<T>((r, j) => {
    resolve = r
    reject = j
  })
  return { promise, resolve, reject }
}
it('keeps the newer person when an earlier detail request fails late', async () => {
  const a = delayed<unknown>()
  const b = delayed<unknown>()
  api.catalog.mockResolvedValue({ writes_enabled: true, organizations: [] })
  api.people.mockResolvedValue({ items: [], total: 0 })
  api.person.mockImplementation((id: string) => (id === 'a' ? a.promise : b.promise))
  const wrapper = simpleMount()
  await flushPromises()
  routeState.query = { person: 'a' }
  await flushPromises()
  routeState.query = { person: 'b' }
  await flushPromises()
  b.resolve({
    id: 'b',
    display_name: '较新人员',
    position: '岗位',
    primary_factory_id: 'f',
    primary_department: 'd',
    identity_mode: 'v2',
    identity_version: 1,
    assignments: [],
    role_bindings: [],
    overrides: [],
    active_assignments_summary: [],
    handover: { count: 0, coverage: [] },
  })
  await flushPromises()
  a.reject(new Error('旧请求失败'))
  await flushPromises()
  expect(wrapper.text()).toContain('较新人员')
  expect(wrapper.text()).not.toContain('旧请求失败')
  wrapper.unmount()
})
it('closes detail when the person query is removed and ignores its late response', async () => {
  const response = delayed<unknown>()
  api.catalog.mockResolvedValue({ organizations: [] })
  api.people.mockResolvedValue({ items: [], total: 0 })
  api.person.mockReturnValue(response.promise)
  const wrapper = simpleMount()
  await flushPromises()
  routeState.query = { person: 'a' }
  await flushPromises()
  routeState.query = {}
  await flushPromises()
  response.resolve({ id: 'a', display_name: '不应显示' })
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('不应显示')
  wrapper.unmount()
})
it('removes sensitive rows on 403 while preserving ordinary retry behavior', async () => {
  api.catalog.mockResolvedValue({ organizations: [] })
  api.people
    .mockResolvedValueOnce({
      items: [
        {
          id: 'p',
          display_name: '原可见人员',
          username: 'account',
          primary_department: 'd',
          status: 'active',
        },
      ],
      total: 1,
    })
    .mockRejectedValueOnce({ response: { status: 403 }, message: '范围已收回' })
  const wrapper = simpleMount()
  await flushPromises()
  expect(wrapper.text()).toContain('原可见人员')
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '刷新')!
    .trigger('click')
  await flushPromises()
  expect(wrapper.text()).not.toContain('原可见人员')
  expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  wrapper.unmount()
})

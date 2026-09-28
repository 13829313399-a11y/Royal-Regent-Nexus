import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import IdentityRecords from '../IdentityRecords.vue'
import type { ChangeRecord } from '@/api/identity'

const api = vi.hoisted(() => ({
  changes: vi.fn(),
  handovers: vi.fn(),
  handoverCandidates: vi.fn(),
  refreshHandover: vi.fn(),
  change: vi.fn(),
  preview: vi.fn(),
  commit: vi.fn(),
}))
vi.mock('@/api/identity', async (original) => ({ ...(await original<object>()), identityApi: api }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/system/iam/requests', fullPath: '/system/iam/requests', query: {} }),
  onBeforeRouteLeave: vi.fn(),
  onBeforeRouteUpdate: vi.fn(),
}))
enableAutoUnmount(afterEach)
const first = {
  id: 'one',
  request_type: 'profile_correction',
  target_user_id: 'person-one',
  requester_user_id: 'admin',
  revision: 1,
  state: 'draft',
  reason: '第一条变更',
  payload: {},
  created_at: '2026-09-28T00:00:00Z',
} as ChangeRecord
const second = { ...first, id: 'two', reason: '第二条变更' }
const handover = {
  items: [{ id: 'item-one', resource_id: '交接单一', status: 'pending', factory_id: 'huaxing' }],
  coverage: [{ module: '内部报价', status: 'covered', basis: '报价责任人' }],
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((r, j) => {
    resolve = r
    reject = j
  })
  return { promise, resolve, reject }
}
const mountView = () =>
  mount(IdentityRecords, {
    global: {
      stubs: {
        IdentityShell: { template: '<div><slot /></div>' },
        AuditTimeline: true,
        AccessImpact: { template: '<div>预览内容</div>' },
        RouterLink: { template: '<a><slot /></a>' },
        teleport: { template: '<div><slot /></div>' },
      },
    },
  })
const button = (wrapper: ReturnType<typeof mountView>, name: string) =>
  wrapper.findAll('button').find((b) => b.text() === name)!
async function selectFirst(wrapper: ReturnType<typeof mountView>) {
  await flushPromises()
  await wrapper.get('.iamx-queue-item').trigger('click')
  await flushPromises()
}
async function tab(wrapper: ReturnType<typeof mountView>, name: string) {
  await wrapper
    .findAll('[role="tab"]')
    .find((b) => b.text() === name)!
    .trigger('mousedown', { button: 0 })
  await flushPromises()
}
beforeEach(() => {
  vi.resetAllMocks()
  api.changes.mockResolvedValue({ items: [first, second], total: 2 })
  api.handovers.mockResolvedValue({ items: [], coverage: [] })
  api.handoverCandidates.mockResolvedValue({ items: [] })
  api.refreshHandover.mockResolvedValue({})
  api.change.mockResolvedValue(first)
})

it('keeps the current request when editing is continued after attempting to switch', async () => {
  const wrapper = mountView()
  await selectFirst(wrapper)
  await wrapper.get('textarea').setValue('原单撤回原因')
  await wrapper.findAll('.iamx-queue-item')[1]!.trigger('click')
  await flushPromises()
  await button(wrapper, '继续编辑').trigger('click')
  await flushPromises()
  expect(wrapper.get('.iamx-record-detail').text()).toContain('第一条变更')
  expect(wrapper.get('textarea').element.value).toBe('原单撤回原因')
})

it('ignores late handover errors and candidates from a previously selected request', async () => {
  const pending = deferred<unknown>()
  api.handovers.mockImplementation((id: string) =>
    id === 'one' ? pending.promise : Promise.resolve({ items: [], coverage: [] }),
  )
  const wrapper = mountView()
  await selectFirst(wrapper)
  await wrapper.findAll('.iamx-queue-item')[1]!.trigger('click')
  await flushPromises()
  pending.reject(new Error('旧单交接失败'))
  await flushPromises()
  expect(wrapper.get('.iamx-record-detail').text()).toContain('第二条变更')
  expect(wrapper.text()).not.toContain('旧单交接失败')
})

it.each(['items', 'candidates'])('clears protected handover details on %s 403', async (stage) => {
  api.changes.mockResolvedValue({ items: [{ ...first, state: 'applied' }], total: 1 })
  api.handovers.mockResolvedValue(handover)
  api.handoverCandidates.mockResolvedValue({
    items: [{ id: 'successor', display_name: '原接管人' }],
  })
  const wrapper = mountView()
  await selectFirst(wrapper)
  await tab(wrapper, '工作交接')
  expect(wrapper.text()).toContain('交接单一')
  expect(wrapper.text()).toContain('原接管人')
  const denied = { response: { status: 403 }, message: '范围已收回' }
  if (stage === 'items') api.handovers.mockRejectedValueOnce(denied)
  else api.handoverCandidates.mockRejectedValueOnce(denied)
  await button(wrapper, '重新评估 / 重试').trigger('click')
  await flushPromises()
  expect(wrapper.text()).not.toContain('交接单一')
  expect(wrapper.text()).not.toContain('原接管人')
  expect(wrapper.text()).not.toContain('报价责任人')
})

it.each([
  { state: 'pending_approval', revision: 2 },
  { state: 'draft', revision: 2 },
])(
  'invalidates stale confirmation after resolving a commit to $state revision $revision',
  async (result) => {
    api.preview.mockResolvedValue({
      preview_token: 'token',
      expires_at: new Date(Date.now() + 60000).toISOString(),
      request_revision: 1,
      requires_approval: true,
    })
    api.commit.mockRejectedValue(new Error('Network Error'))
    api.change.mockResolvedValue({ ...first, ...result })
    const wrapper = mountView()
    await selectFirst(wrapper)
    await tab(wrapper, '权限影响')
    await button(wrapper, '重新核对并预览').trigger('click')
    await flushPromises()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await button(wrapper, '提交审核').trigger('click')
    await flushPromises()
    await button(wrapper, '核查提交结果').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('预览内容')
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)
    expect(api.commit).toHaveBeenCalledTimes(1)
  },
)

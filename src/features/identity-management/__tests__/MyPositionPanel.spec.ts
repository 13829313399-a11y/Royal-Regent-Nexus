import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import MyPositionPanel from '../MyPositionPanel.vue'

const api = vi.hoisted(() => ({ profile: vi.fn(), catalog: vi.fn(), history: vi.fn(), edit: vi.fn(), submit: vi.fn(), withdraw: vi.fn() }))
vi.mock('@/api/positionReviews', () => ({ positionReviewsApi: api, positionStatus: { pending: '待处理' } }))
const auth = reactive({ currentUser: { id: 'employee', identity: { employment_epoch: 1 } }, refreshSession: vi.fn() })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
beforeEach(() => {
  vi.resetAllMocks()
  auth.currentUser.id = 'employee'
  api.profile.mockResolvedValue({ can_submit: true, official_position: { org_unit_id: 'huakang-a', department_code: 'engineering', position: '工程师' }, open_review: null, effective_permission_summary: [] })
  api.catalog.mockResolvedValue({ organizations: [{ id: 'huakang-a', name: '华康A', kind: 'factory', status: 'active', departments: [{ code: 'engineering', name: '工程部' }] }] })
  api.history.mockResolvedValue({ items: [], total: 0 })
})
async function setup() {
  const wrapper = mount(MyPositionPanel, { attachTo: document.body, global: { stubs: { RouterLink: true } } })
  await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '修改岗位')!.trigger('click')
  await flushPromises()
  return wrapper
}
it('cancels without submitting and restores focus to the edit entry', async () => {
  const wrapper = await setup()
  expect(document.activeElement).toBe(wrapper.get('input').element)
  await wrapper.get('input').setValue('取消的草稿')
  const cancel = wrapper.findAll('button').find(button => button.text() === '取消')!
  // In a real browser implicit Enter dispatches the first submit button.
  expect(cancel.attributes('type')).toBe('button')
  await cancel.trigger('click'); await flushPromises()
  expect(api.submit).not.toHaveBeenCalled()
  expect(document.activeElement?.textContent).toContain('修改岗位')
  wrapper.unmount()
})
it('submits the form and moves keyboard focus to the saved result', async () => {
  api.submit.mockResolvedValue({ message: '岗位更新已提交' })
  const wrapper = await setup()
  await wrapper.get('input').setValue('新岗位')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.submit).toHaveBeenCalledWith(expect.objectContaining({ position: '新岗位' }))
  expect(wrapper.find('form').exists()).toBe(false)
  expect(document.activeElement).toBe(wrapper.get('[role="status"]').element)
  wrapper.unmount()
})
it('retains the draft and focuses the error when the source changed', async () => {
  api.submit.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: '申报已变化，请重新核对' } } })
  const wrapper = await setup()
  await wrapper.get('input').setValue('需要保留的草稿')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.get('input').element.value).toBe('需要保留的草稿')
  expect(document.activeElement).toBe(wrapper.get('[role="alert"]').element)
  expect(wrapper.get('[role="alert"]').text()).toContain('申报已变化')
  wrapper.unmount()
})
it('discards an old viewer error when identity changes during the conflict reload', async () => {
  api.submit.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: '旧身份错误' } } })
  const wrapper = await setup()
  let resolve!: (value: unknown) => void
  api.profile.mockReturnValueOnce(new Promise(r => { resolve = r }))
  await wrapper.get('input').setValue('旧身份草稿')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  auth.currentUser.id = 'different-employee'
  await flushPromises()
  const focused = document.activeElement
  resolve({ can_submit: true, official_position: { position: '旧人员岗位' }, effective_permission_summary: [] })
  await flushPromises()
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('旧身份错误')
  expect(document.activeElement).toBe(focused)
  wrapper.unmount()
})

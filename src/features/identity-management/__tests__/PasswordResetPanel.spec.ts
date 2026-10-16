import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import PasswordResetPanel from '../workspace/PasswordResetPanel.vue'
const api = vi.hoisted(() => ({ passwordReset: vi.fn(), approvePasswordResetRequest: vi.fn(), rejectPasswordResetRequest: vi.fn(), reissuePasswordResetRequest: vi.fn(), auth: { currentUser: { id: 'admin', identity: { employment_epoch: 1 } }, authorizationVersion: 1 } }))
vi.mock('@/api/iamWorkspace', () => ({ iamWorkspaceApi: api }))
vi.mock('@/api/system', () => ({ systemApi: api }))
vi.mock('@/stores/auth', async () => { const { reactive } = await import('vue'); const auth = reactive(api.auth); return { useAuthStore: () => ({ get currentUser() { return auth.currentUser }, get authorizationVersion() { return auth.authorizationVersion }, can: () => true }) } })
enableAutoUnmount(afterEach)
const request = { id: 'reset', display_name: '找回测试人', username: 'qa', status: 'pending', issue_count: 0, available_actions: ['approve', 'reject'], matched_user: { display_name: '找回测试人', username: 'qa', status: 'active' }, match_checks: {}, can_reopen: false }
beforeEach(() => { vi.clearAllMocks(); reactive(api.auth).currentUser.id = 'admin'; reactive(api.auth).authorizationVersion = 1; api.passwordReset.mockResolvedValue({ ...request }); api.approvePasswordResetRequest.mockRejectedValue({ response: { status: 408 } }) })
async function setup() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PasswordResetPanel, props: { requestId: 'reset' } }, { path: '/other', component: { template: '<div>other</div>' } }] })
  await router.push('/'); await router.isReady()
  const wrapper = mount(RouterView, { global: { plugins: [router] } }); await flushPromises()
  return { wrapper, router }
}
const button = (wrapper: Awaited<ReturnType<typeof setup>>['wrapper'], text: string) => wrapper.findAll('button').find(b => b.text() === text)!
async function submit(wrapper: Awaited<ReturnType<typeof setup>>['wrapper']) {
  await wrapper.get('input[type=checkbox]').setValue(true); await wrapper.get('textarea').setValue('通过既有线下渠道核实')
  await button(wrapper, '核验并开放找回窗口').trigger('click'); await flushPromises()
}
it.each([408, 500])('keeps uncertain result locked after %s until an observed state changes', async status => {
  api.approvePasswordResetRequest.mockRejectedValue({ response: { status } })
  const { wrapper, router } = await setup(); await submit(wrapper)
  await router.push('/other'); expect(router.currentRoute.value.path).toBe('/')
  await button(wrapper, '核查找回申请结果').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('暂未观察到状态变化')
  expect(button(wrapper, '核验并开放找回窗口').attributes('disabled')).toBeDefined()
  api.passwordReset.mockResolvedValue({ ...request, status: 'approved', issue_count: 1, available_actions: [] })
  await button(wrapper, '核查找回申请结果').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('已开放找回，待本人完成')
  expect(api.approvePasswordResetRequest).toHaveBeenCalledTimes(1)
  await router.push('/other'); expect(router.currentRoute.value.path).toBe('/other')
})
it('preserves only the pending anchor on same-account authorization refresh and drops it for another account', async () => {
  const { wrapper } = await setup(); await submit(wrapper)
  api.passwordReset.mockRejectedValue({ response: { status: 403 } })
  reactive(api.auth).authorizationVersion++; await flushPromises()
  expect(wrapper.text()).not.toContain('找回测试人'); expect(wrapper.text()).toContain('核查找回申请结果')
  reactive(api.auth).currentUser.id = 'other'; await flushPromises()
  expect(wrapper.text()).not.toContain('核查找回申请结果')
})
it('has no review buttons when server write capabilities are disabled', async () => {
  api.passwordReset.mockResolvedValue({ ...request, available_actions: [] })
  const { wrapper } = await setup()
  expect(wrapper.find('textarea').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('核验并开放找回窗口')
  expect(api.approvePasswordResetRequest).not.toHaveBeenCalled()
})

it('retries the original verified intent and issue counter after a lost request', async () => {
  const { wrapper, router } = await setup(); await submit(wrapper)
  expect(wrapper.get('textarea').attributes('maxlength')).toBe('1000')
  const initial = api.approvePasswordResetRequest.mock.calls[0]
  expect(initial?.[1]).toMatchObject({ expected_issue_count: 0, identity_verified: true })
  api.approvePasswordResetRequest.mockResolvedValue({ request: { ...request, status: 'approved', issue_count: 1 } })
  await button(wrapper, '使用原处理内容重试').trigger('click'); await flushPromises()
  expect(api.approvePasswordResetRequest.mock.calls[1]).toEqual(initial)
  expect(wrapper.text()).toContain('找回窗口已开放')
  await router.push('/other'); expect(router.currentRoute.value.path).toBe('/other')
})
it('reads back a completed approval before retrying and never opens another window', async () => {
  const { wrapper } = await setup(); await submit(wrapper)
  api.passwordReset.mockResolvedValue({ ...request, status: 'approved', issue_count: 1, available_actions: [] })
  await button(wrapper, '使用原处理内容重试').trigger('click'); await flushPromises()
  expect(api.approvePasswordResetRequest).toHaveBeenCalledTimes(1)
  expect(wrapper.text()).toContain('已读取最新处理结果')
})

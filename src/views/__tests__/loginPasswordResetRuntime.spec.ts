import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LoginView from '../LoginView.vue'

const authMocks = vi.hoisted(() => ({
  requestPasswordReset: vi.fn(),
  getPasswordResetClaim: vi.fn(),
}))
const routerPushMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/auth', () => ({
  authApi: {
    requestPasswordReset: authMocks.requestPasswordReset,
    getPasswordResetClaim: authMocks.getPasswordResetClaim,
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn(), push: routerPushMock }),
}))

describe('LoginView password reset request', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    authMocks.requestPasswordReset.mockResolvedValue({
      status: 'submitted',
      message: '申请已提交。请保留当前浏览器，管理员审核通过后可在此直接设置新密码。',
      request_id: 'password-reset-1',
    })
    authMocks.getPasswordResetClaim.mockResolvedValue({
      status: 'none', request_id: '', can_complete: false, expires_at: '', message: '未找到凭证',
    })
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
    vi.unstubAllGlobals()
  })

  it('shows the missing contact error beside the action and focuses the field before submitting', async () => {
    const wrapper = mount(LoginView, {
      attachTo: document.body,
      global: {
        plugins: [createPinia()],
        stubs: {
          AuthAmbientGrid: true,
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    const passwordHelpButton = wrapper.findAll('button').find((button) => button.text().includes('忘记密码'))
    expect(passwordHelpButton).toBeDefined()
    await passwordHelpButton!.trigger('click')
    const dialog = wrapper.get('[role="dialog"]')
    await dialog.get('input[autocomplete="username"]').setValue('admin')
    await dialog.get('input[autocomplete="name"]').setValue('系统管理员')

    await dialog.get('form').trigger('submit')
    await flushPromises()

    const contactInput = dialog.get('input[autocomplete="email"]')
    const feedback = dialog.get('#password-reset-feedback')
    expect(authMocks.requestPasswordReset).not.toHaveBeenCalled()
    expect(feedback.attributes('role')).toBe('alert')
    expect(feedback.text()).toContain('请填写联系电话或邮箱，方便管理员核验')
    expect(contactInput.attributes('aria-invalid')).toBe('true')
    expect(document.activeElement).toBe(contactInput.element)

    await contactInput.setValue('13800000000')
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(authMocks.requestPasswordReset).toHaveBeenCalledWith({
      username: 'admin',
      display_name: '系统管理员',
      contact: '13800000000',
      note: '',
    })
    expect(dialog.text()).toContain('申请已提交')
    expect(dialog.text()).toContain('请保留当前浏览器')
    expect(dialog.text()).toContain('password-reset-1')
    wrapper.unmount()
  })

  it('shows an approved same-browser claim and opens the public completion page', async () => {
    authMocks.getPasswordResetClaim.mockResolvedValue({
      status: 'approved',
      request_id: 'password-reset-approved',
      can_complete: true,
      expires_at: '2026-08-19T18:00:00+08:00',
      message: '申请已通过，请在有效期内设置新密码',
    })
    const wrapper = mount(LoginView, {
      attachTo: document.body,
      global: {
        plugins: [createPinia()],
        stubs: { AuthAmbientGrid: true, RouterLink: { template: '<a><slot /></a>' } },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('密码重置申请已通过')
    const completionButton = wrapper.findAll('button').find((button) => button.text().includes('立即设置新密码'))
    await completionButton!.trigger('click')
    expect(routerPushMock).toHaveBeenCalledWith({ name: 'reset-password' })
    wrapper.unmount()
  })
})

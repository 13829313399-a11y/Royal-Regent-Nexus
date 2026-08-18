import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LoginView from '../LoginView.vue'

const requestPasswordResetMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/auth', () => ({
  authApi: {
    requestPasswordReset: requestPasswordResetMock,
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn() }),
}))

describe('LoginView password reset request', () => {
  beforeEach(() => {
    localStorage.clear()
    requestPasswordResetMock.mockReset()
    requestPasswordResetMock.mockResolvedValue({
      status: 'submitted',
      message: '密码重置申请已提交，请等待管理员核验处理',
      request_id: 'password-reset-1',
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
    expect(requestPasswordResetMock).not.toHaveBeenCalled()
    expect(feedback.attributes('role')).toBe('alert')
    expect(feedback.text()).toContain('请填写联系电话或邮箱，方便管理员核验')
    expect(contactInput.attributes('aria-invalid')).toBe('true')
    expect(document.activeElement).toBe(contactInput.element)

    await contactInput.setValue('13800000000')
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(requestPasswordResetMock).toHaveBeenCalledWith({
      username: 'admin',
      display_name: '系统管理员',
      contact: '13800000000',
      note: '',
    })
    expect(dialog.text()).toContain('申请已提交')
    expect(dialog.text()).toContain('password-reset-1')
  })
})

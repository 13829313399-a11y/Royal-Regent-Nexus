import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PasswordResetCompleteView from '../PasswordResetCompleteView.vue'

const authMocks = vi.hoisted(() => ({
  getPasswordResetClaim: vi.fn(),
  completePasswordResetClaim: vi.fn(),
}))
const routerReplaceMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/auth', () => ({ authApi: authMocks }))
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: routerReplaceMock }) }))

function mountView() {
  return mount(PasswordResetCompleteView, {
    global: { stubs: { AuthAmbientGrid: true } },
  })
}

describe('PasswordResetCompleteView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    authMocks.getPasswordResetClaim.mockResolvedValue({
      status: 'approved',
      request_id: 'password-reset-1',
      can_complete: true,
      expires_at: '2026-08-19T18:00:00+08:00',
      message: '申请已通过，请设置新密码',
    })
    authMocks.completePasswordResetClaim.mockResolvedValue({
      status: 'completed',
      message: '密码已成功重置，请使用新密码登录',
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not show the form until the same-browser claim is approved', async () => {
    authMocks.getPasswordResetClaim.mockResolvedValue({
      status: 'pending',
      request_id: 'password-reset-1',
      can_complete: false,
      expires_at: '',
      message: '申请正在等待管理员审核',
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('申请等待管理员审核')
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('刷新状态')
    wrapper.unmount()
  })

  it('blocks mismatched passwords before calling the API', async () => {
    const wrapper = mountView()
    await flushPromises()
    const inputs = wrapper.findAll('input[autocomplete="new-password"]')
    await inputs[0].setValue('FormalPass456!')
    await inputs[1].setValue('DifferentPass789!')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.text()).toContain('两次输入的新密码不一致')
    expect(authMocks.completePasswordResetClaim).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('completes without an old password and returns to login', async () => {
    const wrapper = mountView()
    await flushPromises()
    const inputs = wrapper.findAll('input[autocomplete="new-password"]')
    await inputs[0].setValue('FormalPass456!')
    await inputs[1].setValue('FormalPass456!')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(authMocks.completePasswordResetClaim).toHaveBeenCalledWith({
      new_password: 'FormalPass456!',
      confirm_password: 'FormalPass456!',
    })
    expect(wrapper.text()).toContain('密码已成功重置')
    expect(wrapper.text()).not.toContain('当前密码')
    await vi.advanceTimersByTimeAsync(1200)
    expect(routerReplaceMock).toHaveBeenCalledWith({ name: 'login' })
    wrapper.unmount()
  })

  it('tells a browser without a claim to submit again', async () => {
    authMocks.getPasswordResetClaim.mockResolvedValue({
      status: 'none',
      request_id: '',
      can_complete: false,
      expires_at: '',
      message: '当前浏览器没有找到原申请凭证，请重新提交密码重置申请。',
    })
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('未找到原设备申请')
    expect(wrapper.text()).toContain('重新提交密码重置申请')
    expect(wrapper.find('form').exists()).toBe(false)
    wrapper.unmount()
  })
})

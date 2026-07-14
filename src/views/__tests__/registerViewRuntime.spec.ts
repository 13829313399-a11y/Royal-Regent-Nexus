import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RegisterView from '../RegisterView.vue'

const registerMock = vi.hoisted(() => vi.fn())
const routerReplaceMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/auth', () => ({
  authApi: {
    register: registerMock,
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({
    replace: routerReplaceMock,
  }),
}))

describe('RegisterView position flow', () => {
  beforeEach(() => {
    registerMock.mockReset()
    registerMock.mockResolvedValue({ status: 'pending', message: '账号申请已提交，请等待管理员审批' })
    routerReplaceMock.mockReset()
  })

  it('submits an arbitrary employee position without replacing it with a system role', async () => {
    const wrapper = mount(RegisterView)

    await wrapper.get('input[autocomplete="username"]').setValue(' tech-001 ')
    await wrapper.get('input[autocomplete="name"]').setValue(' 张三 ')
    const passwordInputs = wrapper.findAll('input[type="password"]')
    await passwordInputs[0]!.setValue('Strong123')
    await passwordInputs[1]!.setValue('Strong123')
    await wrapper.get('input[autocomplete="tel"]').setValue(' 13800000000 ')
    await wrapper.get('select').setValue('huaxing')
    await wrapper.findAll('select')[1]!.setValue('engineering')
    await wrapper.get('input[autocomplete="organization-title"]').setValue(' 工程部技术员 ')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(registerMock).toHaveBeenCalledWith({
      username: 'tech-001',
      display_name: '张三',
      password: 'Strong123',
      confirm_password: 'Strong123',
      phone: '13800000000',
      email: '',
      factory_id: 'huaxing',
      department: 'engineering',
      position: '工程部技术员',
    })
    expect(wrapper.text()).toContain('账号申请已提交，请等待管理员审批')
  })
})

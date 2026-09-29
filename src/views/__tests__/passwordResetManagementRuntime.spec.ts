import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SystemUserManagementView from '../SystemUserManagementView.vue'

enableAutoUnmount(afterEach)

const apiMocks = vi.hoisted(() => ({
  listRegistrationRequests: vi.fn(),
  listUsers: vi.fn(),
  listSystemPositions: vi.fn(),
  listPasswordResetRequests: vi.fn(),
  getPasswordResetRequest: vi.fn(),
  approvePasswordResetRequest: vi.fn(),
  rejectPasswordResetRequest: vi.fn(),
  reissuePasswordResetRequest: vi.fn(),
  approveRegistrationRequest: vi.fn(),
  rejectRegistrationRequest: vi.fn(),
  updateUserStatus: vi.fn(),
}))

vi.mock('vue-router', () => ({
  onBeforeRouteLeave: vi.fn(),
  onBeforeRouteUpdate: vi.fn(),
  useRouter: () => ({ replace: vi.fn() }),
  useRoute: () => ({ query: { tab: 'password-reset', request_id: 'password-reset-1' } }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    can: () => true,
    currentUser: { username: 'admin', display_name: '系统管理员' },
  }),
}))

vi.mock('@/api/identity', () => ({ identityApi: { catalog: async () => ({ organizations: [] }) } }))

vi.mock('@/api/system', () => ({ systemApi: apiMocks }))

const matchedRequest = {
  id: 'password-reset-1',
  user_id: 'user-employee',
  username: 'employee',
  display_name: '员工甲',
  contact: '13800000000',
  note: '华兴，工程部',
  factory_id: 'huaxing',
  department: 'engineering',
  status: 'pending',
  reviewer_user_id: null,
  review_comment: '',
  notification_id: 'notification-1',
  submitted_at: '2026-08-02T10:00:00+08:00',
  approved_at: '',
  expires_at: '',
  completed_at: '',
  rejected_at: '',
  created_at: '2026-08-02T10:00:00+08:00',
  updated_at: '2026-08-02T10:00:00+08:00',
  issue_count: 0,
  matched_user: {
    id: 'user-employee',
    username: 'employee',
    display_name: '员工甲',
    status: 'active',
    factory_id: 'huaxing',
    department: 'engineering',
    position: '工程师',
    phone: '13800000000',
    email: 'employee@example.com',
  },
  match_checks: { username: true, display_name: true, contact: true, scope: true },
} as const

function mountView() {
  return mount(SystemUserManagementView, {
    global: {
      stubs: {
        teleport: { template: '<div><slot /></div>' },
        RouterLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('password reset management runtime', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listRegistrationRequests.mockResolvedValue([])
    apiMocks.listUsers.mockResolvedValue([])
    apiMocks.listSystemPositions.mockResolvedValue([])
    apiMocks.listPasswordResetRequests.mockResolvedValue([matchedRequest])
    apiMocks.getPasswordResetRequest.mockResolvedValue(matchedRequest)
    apiMocks.approvePasswordResetRequest.mockResolvedValue({
      request: { ...matchedRequest, status: 'approved', issue_count: 1 },
      expires_at: '2026-08-03T10:00:00+08:00',
      message: '已批准。申请人可在提交申请的原浏览器中设置新密码。',
    })
  })

  it('requires identity confirmation and approves without displaying any secret', async () => {
    const wrapper = mountView()
    await flushPromises()

    const approveButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('批准并开放自助改密'))
    await approveButton!.trigger('click')
    await wrapper
      .get('textarea[placeholder="例如：已电话核验员工身份"]')
      .setValue('已电话核验员工身份')
    const confirmButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('确认批准'))
    expect(confirmButton!.attributes('disabled')).toBeDefined()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await confirmButton!.trigger('click')
    await flushPromises()

    expect(apiMocks.approvePasswordResetRequest).toHaveBeenCalledWith('password-reset-1', {
      review_comment: '已电话核验员工身份',
      identity_verified: true,
    })
    expect(wrapper.text()).toContain('已批准。申请人可在提交申请的原浏览器中设置新密码。')
    expect(wrapper.text()).not.toContain('复制临时密码')
    expect(wrapper.findAll('button').some((button) => button.text().includes('复制'))).toBe(false)
  })

  it('never offers approval when the request has no matched system user', async () => {
    const unmatched = { ...matchedRequest, user_id: null, matched_user: null }
    apiMocks.getPasswordResetRequest.mockResolvedValue(unmatched)
    apiMocks.listPasswordResetRequests.mockResolvedValue([unmatched])
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('未匹配系统账号，不能批准')
    expect(
      wrapper.findAll('button').some((button) => button.text().includes('批准并开放自助改密')),
    ).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text().includes('驳回'))).toBe(true)
  })

  it('labels legacy requests as requiring a fresh submission', async () => {
    const legacy = { ...matchedRequest, status: 'legacy_invalid' }
    apiMocks.getPasswordResetRequest.mockResolvedValue(legacy)
    apiMocks.listPasswordResetRequests.mockResolvedValue([legacy])
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('旧版流程')
    expect(wrapper.text()).toContain('重新提交密码重置申请')
    expect(
      wrapper.findAll('button').some((button) => button.text().includes('批准并开放自助改密')),
    ).toBe(false)
  })
  it('never substitutes another account for an unavailable explicit request link', async () => {
    apiMocks.getPasswordResetRequest.mockRejectedValue({ response: { status: 404 } })
    apiMocks.listPasswordResetRequests.mockResolvedValue([
      { ...matchedRequest, id: 'different-request', display_name: '其他可见人员' },
    ])
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('指定申请不存在或不在当前可见范围')
    expect(wrapper.findAll('button').some((b) => b.text().includes('批准并开放自助改密'))).toBe(
      false,
    )
    wrapper.unmount()
  })
})

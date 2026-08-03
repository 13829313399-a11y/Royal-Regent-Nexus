import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SystemUserManagementView from '../SystemUserManagementView.vue'

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
  useRoute: () => ({ query: { tab: 'password-reset', request_id: 'password-reset-1' } }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    can: () => true,
    currentUser: { username: 'admin', display_name: '系统管理员' },
  }),
}))

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
    id: 'user-employee', username: 'employee', display_name: '员工甲', status: 'active',
    factory_id: 'huaxing', department: 'engineering', position: '工程师',
    phone: '13800000000', email: 'employee@example.com',
  },
  match_checks: { username: true, display_name: true, contact: true, scope: true },
} as const

function mountView() {
  return mount(SystemUserManagementView, {
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
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
      temporary_password: 'T3mp!Safe-Only',
      expires_at: '2026-08-03T10:00:00+08:00',
    })
  })

  it('shows the one-time password after approval, copies it, and clears it on close', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    const wrapper = mountView()
    await flushPromises()

    const approveButton = wrapper.findAll('button').find((button) => button.text().includes('通过并生成临时密码'))
    await approveButton!.trigger('click')
    await wrapper.get('textarea[placeholder="例如：已电话核验员工身份"]').setValue('已电话核验员工身份')
    const confirmButton = wrapper.findAll('button').find((button) => button.text().includes('确认批准'))
    await confirmButton!.trigger('click')
    await flushPromises()

    expect(apiMocks.approvePasswordResetRequest).toHaveBeenCalledWith(
      'password-reset-1',
      { review_comment: '已电话核验员工身份' },
    )
    expect(wrapper.text()).toContain('T3mp!Safe-Only')
    const copyButton = wrapper.findAll('button').find((button) => button.text().includes('复制'))
    await copyButton!.trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('T3mp!Safe-Only')

    const closeButton = wrapper.findAll('button').find((button) => button.text().includes('关闭并清除'))
    await closeButton!.trigger('click')
    expect(wrapper.text()).not.toContain('T3mp!Safe-Only')
  })

  it('never offers approval when the request has no matched system user', async () => {
    const unmatched = { ...matchedRequest, user_id: null, matched_user: null }
    apiMocks.getPasswordResetRequest.mockResolvedValue(unmatched)
    apiMocks.listPasswordResetRequests.mockResolvedValue([unmatched])
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('未匹配系统账号，不能批准')
    expect(wrapper.findAll('button').some((button) => button.text().includes('通过并生成临时密码'))).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text().includes('驳回'))).toBe(true)
  })
})

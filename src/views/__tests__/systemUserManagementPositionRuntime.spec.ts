import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SystemUserManagementView from '../SystemUserManagementView.vue'

const listRegistrationRequestsMock = vi.hoisted(() => vi.fn())
const listUsersMock = vi.hoisted(() => vi.fn())
const listRolesMock = vi.hoisted(() => vi.fn())
const listNotificationsMock = vi.hoisted(() => vi.fn())
const approveRegistrationRequestMock = vi.hoisted(() => vi.fn())
const rejectRegistrationRequestMock = vi.hoisted(() => vi.fn())
const updateUserStatusMock = vi.hoisted(() => vi.fn())
const resetUserPasswordMock = vi.hoisted(() => vi.fn())
const updateNotificationMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
}))

vi.mock('@/api/system', () => ({
  systemApi: {
    listRegistrationRequests: listRegistrationRequestsMock,
    listUsers: listUsersMock,
    listRoles: listRolesMock,
    listNotifications: listNotificationsMock,
    approveRegistrationRequest: approveRegistrationRequestMock,
    rejectRegistrationRequest: rejectRegistrationRequestMock,
    updateUserStatus: updateUserStatusMock,
    resetUserPassword: resetUserPasswordMock,
    updateNotification: updateNotificationMock,
  },
}))

const pendingRequest = {
  id: 'registration-1',
  user_id: 'user-1',
  username: 'tech-001',
  display_name: '张三',
  phone: '13800000000',
  email: '',
  factory_id: 'huaxing',
  department: 'engineering',
  position: '工程部技术员',
  status: 'pending',
  reviewer_user_id: '',
  review_comment: '',
  submitted_at: '2026-07-14T10:00:00',
  reviewed_at: '',
  created_at: '2026-07-14T10:00:00',
  updated_at: '2026-07-14T10:00:00',
  recommended_role_ids: ['engineer'],
}

const roles = [
  {
    id: 'engineer',
    code: 'engineer',
    name: '工程师',
    description: '工程部基础业务权限',
    applicable_departments: ['engineering'],
    requires_global_factory: false,
    scope_guidance: '工程部',
  },
  {
    id: 'molding_production_observer',
    code: 'molding_production_observer',
    name: '生产任务观察员',
    description: '只读生产任务',
    applicable_departments: ['production'],
    requires_global_factory: false,
    scope_guidance: '生产部',
  },
  {
    id: 'group_molding_readonly',
    code: 'group_molding_readonly',
    name: '集团啤办只读',
    description: '集团范围只读',
    applicable_departments: ['*'],
    requires_global_factory: true,
    scope_guidance: '全部厂区',
  },
]

function mountView() {
  return mount(SystemUserManagementView, {
    global: {
      stubs: {
        RouterLink: {
          template: '<a><slot /></a>',
        },
      },
    },
  })
}

describe('SystemUserManagementView position approval', () => {
  beforeEach(() => {
    listRegistrationRequestsMock.mockReset()
    listRegistrationRequestsMock.mockResolvedValue([pendingRequest])
    listUsersMock.mockReset()
    listUsersMock.mockResolvedValue([])
    listRolesMock.mockReset()
    listRolesMock.mockResolvedValue(roles)
    listNotificationsMock.mockReset()
    listNotificationsMock.mockResolvedValue([])
    approveRegistrationRequestMock.mockReset()
    approveRegistrationRequestMock.mockResolvedValue({ ...pendingRequest, status: 'approved' })
    rejectRegistrationRequestMock.mockReset()
    updateUserStatusMock.mockReset()
    resetUserPasswordMock.mockReset()
    updateNotificationMock.mockReset()
  })

  it('keeps the confirmed position separate from the selected permission role', async () => {
    const wrapper = mountView()
    await flushPromises()

    const positionInput = wrapper.get('input[aria-label="确认职位"]')
    expect((positionInput.element as HTMLInputElement).value).toBe('工程部技术员')
    await positionInput.setValue('  高级工程技术员  ')

    const approveButton = wrapper.findAll('button').find((button) => button.text().includes('通过并开通'))
    expect(approveButton).toBeDefined()
    await approveButton!.trigger('click')
    await flushPromises()

    expect(approveRegistrationRequestMock).toHaveBeenCalledWith('registration-1', {
      role_assignments: [
        { role_id: 'engineer', factory_id: 'huaxing', department: 'engineering' },
        { role_id: 'molding_production_observer', factory_id: 'huaxing', department: 'production' },
        { role_id: 'group_molding_readonly', factory_id: '*', department: '*' },
      ],
      review_comment: '',
      position: '高级工程技术员',
    })
  })

  it('blocks approval when the administrator clears the confirmed position', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[aria-label="确认职位"]').setValue('   ')
    const approveButton = wrapper.findAll('button').find((button) => button.text().includes('通过并开通'))
    await approveButton!.trigger('click')

    expect(wrapper.text()).toContain('请输入确认职位')
    expect(approveRegistrationRequestMock).not.toHaveBeenCalled()
  })
})

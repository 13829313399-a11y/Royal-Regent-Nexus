import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SystemUserManagementView from '../SystemUserManagementView.vue'

const listRegistrationRequestsMock = vi.hoisted(() => vi.fn())
const listUsersMock = vi.hoisted(() => vi.fn())
const listSystemPositionsMock = vi.hoisted(() => vi.fn())
const listNotificationsMock = vi.hoisted(() => vi.fn())
const approveRegistrationRequestMock = vi.hoisted(() => vi.fn())
const rejectRegistrationRequestMock = vi.hoisted(() => vi.fn())
const updateUserStatusMock = vi.hoisted(() => vi.fn())
const resetUserPasswordMock = vi.hoisted(() => vi.fn())
const updateNotificationMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))

vi.mock('@/api/system', () => ({
  systemApi: {
    listRegistrationRequests: listRegistrationRequestsMock,
    listUsers: listUsersMock,
    listSystemPositions: listSystemPositionsMock,
    listNotifications: listNotificationsMock,
    approveRegistrationRequest: approveRegistrationRequestMock,
    rejectRegistrationRequest: rejectRegistrationRequestMock,
    updateUserStatus: updateUserStatusMock,
    resetUserPassword: resetUserPasswordMock,
    updateNotification: updateNotificationMock,
  },
}))

const pendingRequest = {
  id: 'registration-1', user_id: 'user-1', username: 'tech-001', display_name: '张三',
  phone: '13800000000', email: '', factory_id: 'huaxing', department: 'engineering',
  position: '工程部技术员', status: 'pending', reviewer_user_id: '', review_comment: '',
  submitted_at: '2026-07-14T10:00:00', reviewed_at: '', created_at: '2026-07-14T10:00:00',
  updated_at: '2026-07-14T10:00:00', recommended_role_ids: ['position_engineering_engineer'],
}

const positions = [
  {
    id: 'position_engineering_engineer', code: 'position_engineering_engineer', name: '工程师', description: '工程部基础业务权限',
    applicable_departments: ['engineering'], requires_global_factory: false, scope_guidance: '工程部',
    is_system_position: true, position_department: 'engineering', position_department_name: '工程部',
    position_sort_order: 30, permission_count: 6,
  },
  {
    id: 'position_engineering_supervisor', code: 'position_engineering_supervisor', name: '主管', description: '工程审核权限',
    applicable_departments: ['engineering'], requires_global_factory: false, scope_guidance: '工程部',
    is_system_position: true, position_department: 'engineering', position_department_name: '工程部',
    position_sort_order: 20, permission_count: 5,
  },
  {
    id: 'position_production_manager', code: 'position_production_manager', name: '生产经理', description: '生产管理权限',
    applicable_departments: ['production'], requires_global_factory: false, scope_guidance: '生产部（啤喷装）',
    is_system_position: true, position_department: 'production', position_department_name: '生产部（啤喷装）',
    position_sort_order: 10, permission_count: 5,
  },
  {
    id: 'position_production_clerk', code: 'position_production_clerk', name: '生产文员', description: '生产资料权限',
    applicable_departments: ['production'], requires_global_factory: false, scope_guidance: '生产部（啤喷装）',
    is_system_position: true, position_department: 'production', position_department_name: '生产部（啤喷装）',
    position_sort_order: 30, permission_count: 0,
  },
]

function mountView() {
  return mount(SystemUserManagementView, {
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

describe('SystemUserManagementView registration approval', () => {
  beforeEach(() => {
    listRegistrationRequestsMock.mockReset().mockResolvedValue([pendingRequest])
    listUsersMock.mockReset().mockResolvedValue([])
    listSystemPositionsMock.mockReset().mockResolvedValue(positions)
    listNotificationsMock.mockReset().mockResolvedValue([])
    approveRegistrationRequestMock.mockReset().mockResolvedValue({ ...pendingRequest, status: 'approved' })
    rejectRegistrationRequestMock.mockReset()
    updateUserStatusMock.mockReset()
    resetUserPasswordMock.mockReset()
    updateNotificationMock.mockReset()
  })

  it('submits corrected profile data and one system position without role assignments', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[aria-label="确认姓名"]').setValue(' 张小明 ')
    await wrapper.get('input[aria-label="确认职位"]').setValue(' 高级工程技术员 ')
    await wrapper.get('select[aria-label="选择内置权限职位"]').setValue('position_engineering_supervisor')

    const selectedSummary = wrapper.get('[data-testid="selected-system-position-summary"]')
    expect(selectedSummary.text()).toContain('工程部 · 主管')
    expect(selectedSummary.text()).toContain('工程审核权限')
    expect(selectedSummary.text()).toContain('5 项权限')

    const approveButton = wrapper.findAll('button').find((button) => button.text().includes('通过并开通'))
    await approveButton!.trigger('click')
    await flushPromises()

    expect(approveRegistrationRequestMock).toHaveBeenCalledWith('registration-1', {
      system_position_role_id: 'position_engineering_supervisor',
      profile: {
        display_name: '张小明', phone: '13800000000', email: '', factory_id: 'huaxing',
        department: 'engineering', position: '高级工程技术员',
      },
      review_comment: '',
    })
    expect(approveRegistrationRequestMock.mock.calls[0]?.[1]).not.toHaveProperty('role_assignments')
  })

  it('groups every system position and allows an explicit cross-department selection after the department changes', async () => {
    const wrapper = mountView()
    await flushPromises()

    const positionSelect = wrapper.get('select[aria-label="选择内置权限职位"]')
    const positionGroups = positionSelect.findAll('optgroup')
    const positionOptions = positionSelect.findAll('option').filter((option) => option.attributes('value'))
    expect(positionGroups.map((group) => group.attributes('label'))).toEqual(['工程部', '生产部（啤喷装）'])
    expect(positionOptions).toHaveLength(4)
    expect((positionSelect.element as HTMLSelectElement).value).toBe('position_engineering_engineer')
    expect(positionSelect.text()).toContain('工程师 · 6 项权限 · 推荐')
    expect(positionSelect.text()).toContain('生产文员 · 权限待配置')
    expect(wrapper.get('[data-testid="selected-system-position-summary"]').text()).toContain('推荐')

    await wrapper.get('select[aria-label="确认部门"]').setValue('production')
    await flushPromises()

    expect((positionSelect.element as HTMLSelectElement).value).toBe('')
    expect(positionSelect.findAll('option').filter((option) => option.attributes('value'))).toHaveLength(4)
    expect(wrapper.find('[data-testid="selected-system-position-summary"]').exists()).toBe(false)

    await positionSelect.setValue('position_engineering_engineer')
    expect(wrapper.get('[data-testid="selected-system-position-summary"]').text()).toContain('工程部 · 工程师')

    const approveButton = wrapper.findAll('button').find((button) => button.text().includes('通过并开通'))
    await approveButton!.trigger('click')
    await flushPromises()
    expect(approveRegistrationRequestMock).toHaveBeenCalledWith('registration-1', {
      system_position_role_id: 'position_engineering_engineer',
      profile: {
        display_name: '张三', phone: '13800000000', email: '', factory_id: 'huaxing',
        department: 'production', position: '工程部技术员',
      },
      review_comment: '',
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

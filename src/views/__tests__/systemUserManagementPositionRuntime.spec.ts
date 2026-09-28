import { reactive } from 'vue'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SystemUserManagementView from '../SystemUserManagementView.vue'

enableAutoUnmount(afterEach)

const listRegistrationRequestsMock = vi.hoisted(() => vi.fn())
const listUsersMock = vi.hoisted(() => vi.fn())
const listSystemPositionsMock = vi.hoisted(() => vi.fn())
const listPasswordResetRequestsMock = vi.hoisted(() => vi.fn())
const approveRegistrationRequestMock = vi.hoisted(() => vi.fn())
const rejectRegistrationRequestMock = vi.hoisted(() => vi.fn())
const updateUserStatusMock = vi.hoisted(() => vi.fn())
const approvePasswordResetRequestMock = vi.hoisted(() => vi.fn())
const rejectPasswordResetRequestMock = vi.hoisted(() => vi.fn())
const reissuePasswordResetRequestMock = vi.hoisted(() => vi.fn())
const canMock = vi.hoisted(() => vi.fn())
const navigation = vi.hoisted(() => ({
  guard: undefined as undefined | (() => Promise<boolean | undefined>),
}))

vi.mock('@/api/identity', () => ({
  identityApi: {
    catalog: async () => ({
      organizations: ['huaxing', 'huakang-a', 'huakang-b', 'huakang-c', 'huakang-d', 'huadeng'].map(
        (id) => ({
          id,
          name: id,
          factory_id: id,
          kind: 'factory',
          status: 'active',
          departments: ['engineering', 'production', 'management', 'pmc-warehouse'].map((code) => ({
            code,
            name: code,
          })),
        }),
      ),
    }),
  },
}))

const routeState = reactive({
  query: {} as Record<string, string>,
  fullPath: '/system/users/registration',
})
vi.mock('vue-router', () => ({
  onBeforeRouteLeave: vi.fn(),
  onBeforeRouteUpdate: (guard: () => Promise<boolean | undefined>) => {
    navigation.guard = guard
  },
  useRoute: () => routeState,
  useRouter: () => ({
    replace: async ({ query }: { query: Record<string, string> }) => {
      if ((await navigation.guard?.()) === false) return
      routeState.query = query
      routeState.fullPath = '/system/users/registration?' + new URLSearchParams(query)
    },
  }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    can: canMock,
    currentUser: { username: 'admin', display_name: '系统管理员' },
  }),
}))

vi.mock('@/api/system', () => ({
  systemApi: {
    listRegistrationRequests: listRegistrationRequestsMock,
    listUsers: listUsersMock,
    listSystemPositions: listSystemPositionsMock,
    listPasswordResetRequests: listPasswordResetRequestsMock,
    approveRegistrationRequest: approveRegistrationRequestMock,
    rejectRegistrationRequest: rejectRegistrationRequestMock,
    updateUserStatus: updateUserStatusMock,
    approvePasswordResetRequest: approvePasswordResetRequestMock,
    rejectPasswordResetRequest: rejectPasswordResetRequestMock,
    reissuePasswordResetRequest: reissuePasswordResetRequestMock,
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
  recommended_role_ids: ['position_engineering_engineer'],
}

const positions = [
  {
    id: 'position_engineering_engineer',
    code: 'position_engineering_engineer',
    name: '工程师',
    description: '工程部基础业务权限',
    applicable_departments: ['engineering'],
    requires_global_factory: false,
    scope_guidance: '工程部',
    is_system_position: true,
    position_department: 'engineering',
    position_department_name: '工程部',
    position_sort_order: 30,
    permission_count: 6,
  },
  {
    id: 'position_engineering_supervisor',
    code: 'position_engineering_supervisor',
    name: '主管',
    description: '工程审核权限',
    applicable_departments: ['engineering'],
    requires_global_factory: false,
    scope_guidance: '工程部',
    is_system_position: true,
    position_department: 'engineering',
    position_department_name: '工程部',
    position_sort_order: 20,
    permission_count: 5,
  },
  {
    id: 'position_production_manager',
    code: 'position_production_manager',
    name: '生产经理',
    description: '生产管理权限',
    applicable_departments: ['production'],
    requires_global_factory: false,
    scope_guidance: '生产部（啤喷装）',
    is_system_position: true,
    position_department: 'production',
    position_department_name: '生产部（啤喷装）',
    position_sort_order: 10,
    permission_count: 5,
  },
  {
    id: 'position_production_clerk',
    code: 'position_production_clerk',
    name: '生产文员',
    description: '生产资料权限',
    applicable_departments: ['production'],
    requires_global_factory: false,
    scope_guidance: '生产部（啤喷装）',
    is_system_position: true,
    position_department: 'production',
    position_department_name: '生产部（啤喷装）',
    position_sort_order: 30,
    permission_count: 0,
  },
]

function mountView() {
  return mount(SystemUserManagementView, {
    global: {
      stubs: {
        RouterLink: { template: '<a><slot /></a>' },
        teleport: { template: '<div><slot /></div>' },
      },
    },
  })
}

describe('SystemUserManagementView registration approval', () => {
  beforeEach(() => {
    navigation.guard = undefined
    routeState.query = {}
    routeState.fullPath = '/system/users/registration'
    canMock.mockReset().mockReturnValue(true)
    listRegistrationRequestsMock.mockReset().mockResolvedValue([pendingRequest])
    listUsersMock.mockReset().mockResolvedValue([])
    listSystemPositionsMock.mockReset().mockResolvedValue(positions)
    listPasswordResetRequestsMock.mockReset().mockResolvedValue([])
    approveRegistrationRequestMock
      .mockReset()
      .mockResolvedValue({ ...pendingRequest, status: 'approved' })
    rejectRegistrationRequestMock.mockReset()
    updateUserStatusMock.mockReset()
    approvePasswordResetRequestMock.mockReset()
    rejectPasswordResetRequestMock.mockReset()
    reissuePasswordResetRequestMock.mockReset()
  })

  it('keeps the deep-linked registration and edits when a request switch is cancelled', async () => {
    routeState.query = { tab: 'pending', request_id: 'registration-1' }
    routeState.fullPath = '/system/users/registration?tab=pending&request_id=registration-1'
    listRegistrationRequestsMock.mockResolvedValue([
      pendingRequest,
      {
        ...pendingRequest,
        id: 'registration-2',
        display_name: '另一位申请人',
        username: 'another-user',
      },
    ])
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('input[aria-label="确认职位"]').setValue('正在核对的职位')
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('另一位申请人'))!
      .trigger('click')
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === '继续编辑')!
      .trigger('click')
    await flushPromises()
    expect(routeState.query.request_id).toBe('registration-1')
    expect(wrapper.get('input[aria-label="确认职位"]').element.value).toBe('正在核对的职位')
  })

  it('keeps the page available without reading or exposing protected account data', async () => {
    canMock.mockImplementation((permission: string) => permission !== 'system:user_manage')

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-testid="system-users-protected-notice"]').text()).toContain(
      '敏感账号资料受保护',
    )
    expect(wrapper.text()).toContain('页面可访问 · 敏感账号资料受保护')
    expect(wrapper.text()).toContain('账号办理')
    expect(listRegistrationRequestsMock).not.toHaveBeenCalled()
    expect(listUsersMock).not.toHaveBeenCalled()
    expect(listSystemPositionsMock).not.toHaveBeenCalled()
    expect(listPasswordResetRequestsMock).not.toHaveBeenCalled()
    expect(wrapper.find('.stats').exists()).toBe(false)
    expect(wrapper.find('.approval-workspace').exists()).toBe(false)
    expect(wrapper.find('.users-panel').exists()).toBe(false)
    const refreshButton = wrapper.findAll('button').find((button) => button.text().includes('刷新'))
    expect(refreshButton?.attributes('disabled')).toBeDefined()
  })

  it('shows system timestamps in Beijing time and reports the oldest pending submission', async () => {
    listRegistrationRequestsMock.mockResolvedValue([
      { ...pendingRequest, submitted_at: '2026-07-14T10:00:00+08:00' },
      {
        ...pendingRequest,
        id: 'registration-older',
        user_id: 'user-older',
        username: 'older-user',
        submitted_at: '2026-07-13T23:30:00Z',
      },
    ])
    listUsersMock.mockResolvedValue([
      {
        id: 'user-1',
        username: 'tech-001',
        display_name: '张三',
        phone: '13800000000',
        email: '',
        status: 'active',
        force_password_change: false,
        last_login_at: '2026-07-18T08:00:00Z',
        created_at: '2026-07-14T02:00:00Z',
        updated_at: '2026-07-18T08:00:00Z',
        roles: [],
        primary_factory_id: 'huaxing',
        primary_department: 'engineering',
        position: '工程师',
      },
    ])
    listPasswordResetRequestsMock.mockResolvedValue([
      {
        id: 'password-reset-1',
        user_id: 'user-1',
        username: 'tech-001',
        display_name: '张三',
        contact: '13800000000',
        note: '忘记密码',
        factory_id: 'huaxing',
        department: 'engineering',
        status: 'pending',
        reviewer_user_id: null,
        review_comment: '',
        notification_id: 'notification-1',
        submitted_at: '2026-07-18T08:05:00Z',
        approved_at: '',
        expires_at: '',
        completed_at: '',
        rejected_at: '',
        created_at: '2026-07-18T08:05:00Z',
        updated_at: '2026-07-18T08:05:00Z',
        issue_count: 0,
        matched_user: {
          id: 'user-1',
          username: 'tech-001',
          display_name: '张三',
          status: 'active',
          factory_id: 'huaxing',
          org_unit_id: 'huaxing',
          business_factory_ids: [],
          department: 'engineering',
          position: '工程师',
          phone: '13800000000',
          email: '',
        },
        match_checks: { username: true, display_name: true, contact: true, scope: true },
      },
    ])

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('最早提交于 2026-07-14 07:30:00')
    expect(wrapper.text()).toContain('2026-07-14 07:30:00')

    const passwordResetTab = wrapper
      .findAll('button')
      .find((button) => button.text().includes('密码找回'))
    await passwordResetTab!.trigger('mousedown', { button: 0 })
    await flushPromises()
    expect(wrapper.text()).toContain('2026-07-18 16:05:00')

    const usersTab = wrapper
      .findAll('button')
      .find((button) => button.text().includes('兼容账号列表'))
    await usersTab!.trigger('mousedown', { button: 0 })
    await flushPromises()
    expect(wrapper.text()).toContain('2026-07-18 16:00:00')
  })

  it('submits corrected profile data and one system position without role assignments', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[aria-label="确认姓名"]').setValue(' 张小明 ')
    await wrapper.get('input[aria-label="确认职位"]').setValue(' 高级工程技术员 ')
    await wrapper
      .get('select[aria-label="选择内置权限职位"]')
      .setValue('position_engineering_supervisor')

    const selectedSummary = wrapper.get('[data-testid="selected-system-position-summary"]')
    expect(selectedSummary.text()).toContain('工程部 · 主管')
    expect(selectedSummary.text()).toContain('工程审核权限')
    expect(selectedSummary.text()).toContain('5 项权限')

    const approveButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('通过并开通'))
    await approveButton!.trigger('click')
    await flushPromises()

    expect(approveRegistrationRequestMock).toHaveBeenCalledWith('registration-1', {
      system_position_role_id: 'position_engineering_supervisor',
      profile: {
        display_name: '张小明',
        phone: '13800000000',
        email: '',
        factory_id: 'huaxing',
        org_unit_id: 'huaxing',
        business_factory_ids: [],
        department: 'engineering',
        position: '高级工程技术员',
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
    const positionOptions = positionSelect
      .findAll('option')
      .filter((option) => option.attributes('value'))
    expect(positionGroups.map((group) => group.attributes('label'))).toEqual([
      '工程部',
      '生产部（啤喷装）',
    ])
    expect(positionOptions).toHaveLength(4)
    expect((positionSelect.element as HTMLSelectElement).value).toBe('')
    expect(positionSelect.text()).toContain('工程师 · 6 项权限 · 推荐')
    expect(positionSelect.text()).toContain('生产文员 · 权限待配置')
    expect(wrapper.find('[data-testid="selected-system-position-summary"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="registration-position-recommendation"]').text()).toContain(
      '推荐仅用于提示，不会自动选中或授权',
    )

    const approveButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('通过并开通'))
    await approveButton!.trigger('click')
    expect(wrapper.text()).toContain('请选择一个内置权限职位')
    expect(approveRegistrationRequestMock).not.toHaveBeenCalled()

    await wrapper.get('select[aria-label="确认部门"]').setValue('production')
    await flushPromises()

    expect((positionSelect.element as HTMLSelectElement).value).toBe('')
    expect(
      positionSelect.findAll('option').filter((option) => option.attributes('value')),
    ).toHaveLength(4)
    expect(wrapper.find('[data-testid="selected-system-position-summary"]').exists()).toBe(false)

    await positionSelect.setValue('position_engineering_engineer')
    expect(wrapper.get('[data-testid="selected-system-position-summary"]').text()).toContain(
      '工程部 · 工程师',
    )

    await approveButton!.trigger('click')
    await flushPromises()
    expect(approveRegistrationRequestMock).toHaveBeenCalledWith('registration-1', {
      system_position_role_id: 'position_engineering_engineer',
      profile: {
        display_name: '张三',
        phone: '13800000000',
        email: '',
        factory_id: 'huaxing',
        org_unit_id: 'huaxing',
        business_factory_ids: [],
        department: 'production',
        position: '工程部技术员',
      },
      review_comment: '',
    })
  })

  it('blocks approval when the administrator clears the confirmed position', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('input[aria-label="确认职位"]').setValue('   ')
    const approveButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('通过并开通'))
    await approveButton!.trigger('click')
    expect(wrapper.text()).toContain('请输入确认职位')
    expect(approveRegistrationRequestMock).not.toHaveBeenCalled()
  })
})

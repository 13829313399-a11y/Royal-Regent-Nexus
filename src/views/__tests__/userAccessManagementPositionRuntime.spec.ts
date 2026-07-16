import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import UserAccessManagementView from '../UserAccessManagementView.vue'

const getUserAccessMock = vi.hoisted(() => vi.fn())
const listSystemPositionsMock = vi.hoisted(() => vi.fn())
const listPermissionsMock = vi.hoisted(() => vi.fn())
const getRoleAccessMock = vi.hoisted(() => vi.fn())
const previewUserSystemPositionMock = vi.hoisted(() => vi.fn())
const commitUserSystemPositionMock = vi.hoisted(() => vi.fn())
const refreshSessionMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { userId: 'user-1' } }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ can: () => true, refreshSession: refreshSessionMock }),
}))

vi.mock('@/api/iam', () => ({
  iamApi: {
    getUserAccess: getUserAccessMock,
    listSystemPositions: listSystemPositionsMock,
    listPermissions: listPermissionsMock,
    getRoleAccess: getRoleAccessMock,
    previewUserSystemPosition: previewUserSystemPositionMock,
    commitUserSystemPosition: commitUserSystemPositionMock,
  },
}))

const positions = [
  {
    id: 'position-engineer', code: 'position_engineering_engineer', name: '工程师',
    description: '工程部基础权限', version: 1, is_protected: false, binding_count: 4,
    permission_count: 1, applicable_departments: ['engineering'], requires_global_factory: false,
    scope_guidance: '工程部', is_system_position: true, position_department: 'engineering',
    position_department_name: '工程部', position_sort_order: 30,
  },
  {
    id: 'position-supervisor', code: 'position_engineering_supervisor', name: '工程部主管',
    description: '工程部审核权限', version: 1, is_protected: false, binding_count: 2,
    permission_count: 1, applicable_departments: ['engineering'], requires_global_factory: false,
    scope_guidance: '工程部', is_system_position: true, position_department: 'engineering',
    position_department_name: '工程部', position_sort_order: 20,
  },
  {
    id: 'position-production-clerk', code: 'position_production_clerk', name: '生产文员',
    description: '生产部（啤喷装）资料权限', version: 1, is_protected: false, binding_count: 1,
    permission_count: 0, applicable_departments: ['production'], requires_global_factory: false,
    scope_guidance: '生产部（啤喷装）', is_system_position: true, position_department: 'production',
    position_department_name: '生产部（啤喷装）', position_sort_order: 30,
  },
]

const access = {
  user: {
    id: 'user-1', username: 'tech-001', display_name: '张三', status: 'active',
    phone: '13800000000', email: '', primary_factory_id: 'huaxing',
    primary_department: 'engineering', position: '技术员', manageable: true,
  },
  profile: {
    primary_factory_id: 'huaxing', primary_department: 'engineering', position: '技术员',
    confirmation_status: 'confirmed',
  },
  authorization_version: 2,
  role_bindings: [],
  overrides: [],
  effective_access: [],
  system_position_role_id: 'position-engineer',
  system_position_role_name: '工程师',
  recommended_system_position_role_id: 'position-engineer',
  legacy_role_count: 2,
  active_override_count: 1,
  cleanup_role_count: 2,
  cleanup_override_count: 1,
}

const permission = {
  code: 'molding_sample:manager_review', name: '啤办经理终审', description: '',
  module_code: 'molding_sample', module_name: '啤办管理', action: 'manager_review',
  risk_level: 'high', scope_type: 'factory_department', status: 'active', sort_order: 1,
  applicable_departments: ['engineering'], requires_global_factory: false, scope_guidance: '本部门',
}

function mountView() {
  return mount(UserAccessManagementView, {
    global: {
      stubs: {
        IamNavigation: { template: '<header />' },
        IamIdentitySummary: { props: ['access'], template: '<section data-testid="identity-summary">{{ access.profile.position }}</section>' },
        RouterLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('UserAccessManagementView system position change', () => {
  beforeEach(() => {
    getUserAccessMock.mockReset().mockResolvedValue(access)
    listSystemPositionsMock.mockReset().mockResolvedValue(positions)
    listPermissionsMock.mockReset().mockResolvedValue([permission])
    getRoleAccessMock.mockReset().mockImplementation(async (roleId: string) => ({
      ...positions.find((position) => position.id === roleId),
      permission_codes: ['molding_sample:manager_review'],
    }))
    previewUserSystemPositionMock.mockReset().mockResolvedValue({
      preview_token: 'preview-1', base_revision: 2,
      before_role_ids: ['legacy-engineer'], before_role_names: ['工程师'],
      after_role_id: 'position-production-clerk', after_role_name: '生产文员',
      removed_role_count: 2, removed_override_count: 1,
      requires_approval: false, high_risk: false,
      diffs: [{
        permission_code: 'molding_sample:manager_review', factory_id: 'huaxing',
        department: 'engineering', before: 'none', after: 'allow', risk_level: 'high',
      }],
      expires_at: '2026-07-16T12:00:00Z',
    })
    commitUserSystemPositionMock.mockReset().mockResolvedValue({
      status: 'committed', authorization_version: 3,
    })
    refreshSessionMock.mockReset().mockResolvedValue(undefined)
  })

  it('previews and commits one selected position while showing historical cleanup', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-testid="identity-summary"]').text()).toBe('技术员')
    expect(wrapper.text()).toContain('当前生效 2 条旧角色、1 条个人特殊权限')
    expect(wrapper.text()).toContain('本次共将清理 2 条普通角色和 1 条个人权限')
    expect(wrapper.get('select[aria-label="选择新的内置权限职位"]').text()).toContain('生产文员')

    await wrapper.get('select[aria-label="选择新的内置权限职位"]').setValue('position-production-clerk')
    await wrapper.get('input[placeholder="例如：员工岗位职责调整为工程主管"]').setValue('职责调整')
    await flushPromises()

    const previewButton = wrapper.findAll('button').find((button) => button.text().includes('预览职位调整'))
    expect(previewButton).toBeDefined()
    await previewButton!.trigger('click')
    await flushPromises()

    expect(previewUserSystemPositionMock).toHaveBeenCalledWith('user-1', {
      base_revision: 2,
      system_position_role_id: 'position-production-clerk',
      reason: '职责调整',
    })
    expect(wrapper.text()).toContain('清理历史角色')
    expect(wrapper.text()).toContain('清理个人特殊权限')
    expect(wrapper.text()).toContain('生产部（啤喷装） · 生产文员')

    const commitButton = wrapper.findAll('button').find((button) => button.text().includes('确认并立即生效'))
    expect(commitButton).toBeDefined()
    await commitButton!.trigger('click')
    await flushPromises()

    expect(commitUserSystemPositionMock).toHaveBeenCalledWith('user-1', 'preview-1', false)
    expect(refreshSessionMock).toHaveBeenCalled()
    expect(wrapper.text()).toContain('权限职位已更换并立即生效')
  })

  it('keeps an existing cross-department system position selected after refresh', async () => {
    getUserAccessMock.mockResolvedValue({
      ...access,
      system_position_role_id: 'position-production-clerk',
      system_position_role_name: '生产文员',
      recommended_system_position_role_id: 'position-engineer',
    })

    const wrapper = mountView()
    await flushPromises()

    const select = wrapper.get('select[aria-label="选择新的内置权限职位"]')
    expect((select.element as HTMLSelectElement).value).toBe('position-production-clerk')
    expect(getRoleAccessMock).toHaveBeenCalledWith('position-production-clerk')
  })

  it('allows cleanup while keeping the same system position', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[placeholder="例如：员工岗位职责调整为工程主管"]').setValue('整理历史授权')
    const cleanupButton = wrapper.findAll('button').find((button) => button.text().includes('预览历史授权清理'))
    expect(cleanupButton).toBeDefined()
    expect(cleanupButton!.attributes('disabled')).toBeUndefined()

    await cleanupButton!.trigger('click')
    await flushPromises()

    expect(previewUserSystemPositionMock).toHaveBeenCalledWith('user-1', {
      base_revision: 2,
      system_position_role_id: 'position-engineer',
      reason: '整理历史授权',
    })
  })

  it('does not silently fall back to the first position when no recommendation matches', async () => {
    getUserAccessMock.mockResolvedValue({
      ...access,
      system_position_role_id: '',
      system_position_role_name: '',
      recommended_system_position_role_id: 'missing-position',
      legacy_role_count: 0,
      active_override_count: 0,
      cleanup_role_count: 0,
      cleanup_override_count: 0,
    })

    const wrapper = mountView()
    await flushPromises()

    const select = wrapper.get('select[aria-label="选择新的内置权限职位"]')
    expect((select.element as HTMLSelectElement).value).toBe('')
    expect(getRoleAccessMock).not.toHaveBeenCalled()
  })

  it('requires primary organization data before showing assignable positions', async () => {
    getUserAccessMock.mockResolvedValue({
      ...access,
      profile: {
        ...access.profile,
        primary_factory_id: '',
        primary_department: '',
        confirmation_status: 'needs_review',
      },
      system_position_role_id: '',
      system_position_role_name: '',
      recommended_system_position_role_id: 'position-engineer',
      legacy_role_count: 0,
      active_override_count: 0,
      cleanup_role_count: 0,
      cleanup_override_count: 0,
    })

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-testid="missing-primary-department"]').text()).toContain('尚未确认主组织资料')
    expect(wrapper.find('select[aria-label="选择新的内置权限职位"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="system-position-action-panel"]').exists()).toBe(false)
    expect(getRoleAccessMock).not.toHaveBeenCalled()
  })

  it('also blocks assignment when the department exists but the factory is missing', async () => {
    getUserAccessMock.mockResolvedValue({
      ...access,
      profile: {
        ...access.profile,
        primary_factory_id: '',
      },
      system_position_role_id: '',
      system_position_role_name: '',
      cleanup_role_count: 0,
      cleanup_override_count: 0,
    })

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-testid="missing-primary-department"]').text()).toContain('补全厂区和部门')
    expect(wrapper.find('select[aria-label="选择新的内置权限职位"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="system-position-action-panel"]').exists()).toBe(false)
    expect(getRoleAccessMock).not.toHaveBeenCalled()
  })
})

import { reactive } from 'vue'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { knownIdentityMode, rememberIdentityMode, setIdentityViewer } from '@/components/iam/workspace/identity-ui-context'
import UserAccessManagementView from '../UserAccessManagementView.vue'

enableAutoUnmount(afterEach)

const getUserAccessMock = vi.hoisted(() => vi.fn())
const listSystemPositionsMock = vi.hoisted(() => vi.fn())
const listPermissionsMock = vi.hoisted(() => vi.fn())
const getRoleAccessMock = vi.hoisted(() => vi.fn())
const previewUserSystemPositionMock = vi.hoisted(() => vi.fn())
const commitUserSystemPositionMock = vi.hoisted(() => vi.fn())
const previewUserAccessMock = vi.hoisted(() => vi.fn())
const commitUserAccessMock = vi.hoisted(() => vi.fn())
const refreshSessionMock = vi.hoisted(() => vi.fn())
const canMock = vi.hoisted(() => vi.fn())
const authMock = vi.hoisted(() => ({
  grants: [] as Array<{ role_id: string; factory_id: string; department: string }>,
}))

const routeState = reactive({ params: { userId: 'user-1' }, query: { identity_mode: '' } })
const viewerState = reactive({ id: '' })
vi.mock('vue-router', () => ({
  onBeforeRouteLeave: vi.fn(),
  onBeforeRouteUpdate: vi.fn(),
  useRoute: () => routeState,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    currentUser: viewerState,
    can: canMock,
    grants: authMock.grants,
    refreshSession: refreshSessionMock,
  }),
}))

vi.mock('@/api/iam', () => ({
  iamApi: {
    getUserAccess: getUserAccessMock,
    listSystemPositions: listSystemPositionsMock,
    listPermissions: listPermissionsMock,
    getRoleAccess: getRoleAccessMock,
    previewUserSystemPosition: previewUserSystemPositionMock,
    commitUserSystemPosition: commitUserSystemPositionMock,
    previewUserAccess: previewUserAccessMock,
    commitUserAccess: commitUserAccessMock,
  },
}))

const fixedRoleFields = {
  scope_mode: 'own_factory',
  is_editable: false,
  source: 'code',
  scope_mode_locked: true,
  definition_version: 'system-positions-v1',
  definition_hash: 'fixed-position-hash',
}

const positions = [
  {
    ...fixedRoleFields,
    id: 'position-engineer',
    code: 'position_engineering_engineer',
    name: '工程师',
    description: '工程部基础权限',
    version: 1,
    is_protected: false,
    binding_count: 4,
    permission_count: 1,
    applicable_departments: ['engineering'],
    requires_global_factory: false,
    scope_guidance: '工程部',
    is_system_position: true,
    position_department: 'engineering',
    position_department_name: '工程部',
    position_sort_order: 30,
  },
  {
    ...fixedRoleFields,
    id: 'position-supervisor',
    code: 'position_engineering_supervisor',
    name: '工程部主管',
    description: '工程部审核权限',
    version: 1,
    is_protected: false,
    binding_count: 2,
    permission_count: 1,
    applicable_departments: ['engineering'],
    requires_global_factory: false,
    scope_guidance: '工程部',
    is_system_position: true,
    position_department: 'engineering',
    position_department_name: '工程部',
    position_sort_order: 20,
  },
  {
    ...fixedRoleFields,
    id: 'position-production-clerk',
    code: 'position_production_clerk',
    name: '生产文员',
    description: '生产部（啤喷装）资料权限',
    version: 1,
    is_protected: false,
    binding_count: 1,
    permission_count: 0,
    applicable_departments: ['production'],
    requires_global_factory: false,
    scope_guidance: '生产部（啤喷装）',
    is_system_position: true,
    position_department: 'production',
    position_department_name: '生产部（啤喷装）',
    position_sort_order: 30,
  },
]

const access = {
  user: {
    id: 'user-1',
    username: 'tech-001',
    display_name: '张三',
    status: 'active',
    phone: '13800000000',
    email: '',
    primary_factory_id: 'huaxing',
    primary_department: 'engineering',
    position: '技术员',
    manageable: true,
  },
  profile: {
    primary_factory_id: 'huaxing',
    primary_department: 'engineering',
    position: '技术员',
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
  code: 'molding_sample:manager_review',
  name: '啤办经理终审',
  description: '',
  module_code: 'molding_sample',
  module_name: '啤办管理',
  action: 'manager_review',
  access_kind: 'operate',
  risk_level: 'high',
  scope_type: 'factory_department',
  status: 'active',
  sort_order: 1,
  applicable_departments: ['engineering'],
  requires_global_factory: false,
  scope_guidance: '本部门',
}

const formerlyHiddenInactivePermission = {
  ...permission,
  code: 'system:access_request',
  name: 'system:access_request',
  description: '提交权限申请。',
  module_code: 'system',
  module_name: '系统管理',
  action: 'access_request',
  status: 'inactive',
  sort_order: 2,
}

const selfReviewPermission = {
  ...permission,
  code: 'internal_quote:self_review',
  name: 'internal_quote:self_review',
  description: '允许审核本人创建且由本人负责的内部报价。',
  module_code: 'internal_quote',
  module_name: '内部报价',
  action: 'self_review',
  applicable_departments: ['sales-business'],
  scope_guidance: '仅业务部',
  sort_order: 3,
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function mountView() {
  return mount(UserAccessManagementView, {
    global: {
      stubs: {
        teleport: { template: '<div><slot /></div>' },
        IamNavigation: { template: '<header />' },
        IamIdentitySummary: {
          props: ['access'],
          template:
            '<section data-testid="identity-summary">实际职位：{{ access.profile.position }}</section>',
        },
        RouterLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('UserAccessManagementView system position change', () => {
  beforeEach(() => {
    setIdentityViewer('reset')
    setIdentityViewer('')
    routeState.params.userId = 'user-1'
    routeState.query.identity_mode = ''
    viewerState.id = ''
    authMock.grants = []
    canMock.mockReset().mockReturnValue(true)
    getUserAccessMock.mockReset().mockResolvedValue(access)
    listSystemPositionsMock.mockReset().mockResolvedValue(positions)
    listPermissionsMock
      .mockReset()
      .mockResolvedValue([permission, formerlyHiddenInactivePermission])
    getRoleAccessMock.mockReset().mockImplementation(async (roleId: string) => ({
      ...positions.find((position) => position.id === roleId),
      permission_codes: ['molding_sample:manager_review', 'system:access_request'],
    }))
    previewUserSystemPositionMock.mockReset().mockResolvedValue({
      preview_token: 'preview-1',
      base_revision: 2,
      before_role_ids: ['legacy-engineer'],
      before_role_names: ['工程师'],
      after_role_id: 'position-production-clerk',
      after_role_name: '生产文员',
      removed_role_count: 2,
      removed_override_count: 1,
      requires_approval: false,
      high_risk: false,
      diffs: [
        {
          permission_code: 'molding_sample:manager_review',
          factory_id: 'huaxing',
          department: 'engineering',
          before: 'none',
          after: 'allow',
          risk_level: 'high',
        },
      ],
      expires_at: '2026-07-16T12:00:00Z',
    })
    commitUserSystemPositionMock.mockReset().mockResolvedValue({
      status: 'committed',
      authorization_version: 3,
    })
    previewUserAccessMock.mockReset().mockResolvedValue({
      preview_token: 'self-review-preview',
      base_revision: 2,
      requires_approval: false,
      high_risk: true,
      diffs: [
        {
          permission_code: 'internal_quote:self_review',
          factory_id: 'huaxing',
          department: 'sales-business',
          before: 'none',
          after: 'allow',
          risk_level: 'high',
        },
      ],
    })
    commitUserAccessMock.mockReset().mockResolvedValue({
      status: 'committed',
      authorization_version: 3,
    })
    refreshSessionMock.mockReset().mockResolvedValue(undefined)
  })

  it('previews and saves supplier read and approval separately from the internal position', async () => {
    authMock.grants = [{ role_id: 'admin', factory_id: '*', department: 'system' }]
    listPermissionsMock.mockResolvedValue(
      ['read', 'edit', 'approve'].map((action, index) => ({
        ...permission,
        code: `carton_supplier:${action}`,
        name: `供应商${action}`,
        module_code: 'carton_supplier',
        action,
        status: 'active',
        sort_order: index + 1,
      })),
    )
    previewUserAccessMock.mockResolvedValue({
      preview_token: 'supplier-preview',
      base_revision: 2,
      requires_approval: false,
      high_risk: true,
      diffs: [
        {
          permission_code: 'carton_supplier:approve',
          factory_id: '*',
          department: '*',
          before: 'none',
          after: 'allow',
          risk_level: 'high',
        },
      ],
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .findAll('[role="tab"]')
      .find((t) => t.text() === '供应商协作')!
      .trigger('mousedown', { button: 0 })
    const card = wrapper.get('[data-testid="supplier-permission-card"]')
    await card.get('input[aria-label="供应商read"]').setValue(true)
    await card.get('input[aria-label="供应商approve"]').setValue(true)
    await card.get('input[aria-label="供应商权限变更原因"]').setValue('开通接单权限')
    await card
      .findAll('button')
      .find((button) => button.text().includes('预览供应商权限变更'))!
      .trigger('click')
    await flushPromises()
    expect(previewUserAccessMock).toHaveBeenCalledWith('user-1', {
      base_revision: 2,
      reason: '开通接单权限',
      overrides: [
        {
          permission_code: 'carton_supplier:read',
          effect: 'allow',
          factory_id: '*',
          department: '*',
        },
        {
          permission_code: 'carton_supplier:approve',
          effect: 'allow',
          factory_id: '*',
          department: '*',
        },
      ],
    })
    expect(previewUserSystemPositionMock).not.toHaveBeenCalled()
    await card.get('input[aria-label="确认供应商高风险权限"]').setValue(true)
    await card
      .findAll('button')
      .find((button) => button.text().includes('确认保存权限'))!
      .trigger('click')
    await flushPromises()
    expect(commitUserAccessMock).toHaveBeenCalledWith('user-1', 'supplier-preview', true)
    expect(refreshSessionMock).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('locks the supplier permission draft while a preview request is pending', async () => {
    authMock.grants = [{ role_id: 'admin', factory_id: '*', department: 'system' }]
    listPermissionsMock.mockResolvedValue(
      ['read', 'edit', 'approve'].map((action, index) => ({
        ...permission,
        code: `carton_supplier:${action}`,
        name: `供应商${action}`,
        module_code: 'carton_supplier',
        action,
        status: 'active',
        sort_order: index + 1,
      })),
    )
    const pending = deferred<Awaited<ReturnType<typeof previewUserAccessMock>>>()
    previewUserAccessMock.mockReturnValueOnce(pending.promise)
    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .findAll('[role="tab"]')
      .find((t) => t.text() === '供应商协作')!
      .trigger('mousedown', { button: 0 })
    const card = wrapper.get('[data-testid="supplier-permission-card"]')
    await card.get('input[aria-label="供应商read"]').setValue(true)
    await card.get('input[aria-label="供应商权限变更原因"]').setValue('只读协同')
    await card
      .findAll('button')
      .find((button) => button.text().includes('预览供应商权限变更'))!
      .trigger('click')
    expect(card.get('input[aria-label="供应商read"]').attributes('disabled')).toBeDefined()
    expect(card.get('input[aria-label="供应商权限变更原因"]').attributes('disabled')).toBeDefined()
    pending.resolve({
      preview_token: 'locked-preview',
      base_revision: 2,
      requires_approval: false,
      high_risk: false,
      diffs: [],
    })
    await flushPromises()
    expect(card.get('input[aria-label="供应商read"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('keeps the page available without reading protected authorization data when access management is denied', async () => {
    canMock.mockReturnValue(false)

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-testid="user-access-protected-notice"]').text()).toContain(
      '权限资料受保护',
    )
    expect(wrapper.text()).toContain('职位选择、变更预览及提交操作均不可用')
    expect(getUserAccessMock).not.toHaveBeenCalled()
    expect(listSystemPositionsMock).not.toHaveBeenCalled()
    expect(listPermissionsMock).not.toHaveBeenCalled()
    expect(getRoleAccessMock).not.toHaveBeenCalled()
    expect(previewUserSystemPositionMock).not.toHaveBeenCalled()
    expect(commitUserSystemPositionMock).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="identity-summary"]').exists()).toBe(false)
    expect(wrapper.find('select[aria-label="选择新的内置权限职位"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="system-position-action-panel"]').exists()).toBe(false)
  })

  it('previews and commits one selected position while showing historical cleanup', async () => {
    const wrapper = mountView()
    await flushPromises()
    if (wrapper.findAll('[role="tab"]').some((t) => t.text() === '旧权限兼容'))
      await wrapper
        .findAll('[role="tab"]')
        .find((t) => t.text() === '旧权限兼容')!
        .trigger('mousedown', { button: 0 })
    await wrapper
      .findAll('[role="tab"]')
      .find((t) => t.text() === '旧权限兼容')!
      .trigger('mousedown', { button: 0 })

    expect(wrapper.get('[data-testid="identity-summary"]').text()).toBe('实际职位：技术员')
    expect(listPermissionsMock).toHaveBeenCalledWith('all')
    expect(wrapper.text()).toContain('权限职位')
    expect(wrapper.get('[data-testid="selected-position-fixed-metadata"]').text()).toContain(
      '代码固定',
    )
    expect(wrapper.get('[data-testid="selected-position-fixed-metadata"]').text()).toContain('本厂')
    expect(wrapper.text()).toContain('system:access_request')
    expect(wrapper.text()).toContain('提交权限申请')
    expect(wrapper.text()).toContain('已停用')
    expect(wrapper.text()).toContain('高风险')
    expect(wrapper.text()).toContain('已包含')
    expect(wrapper.text()).toContain('当前生效 2 条旧角色、1 条个人特殊权限')
    expect(wrapper.text()).toContain('本次共将清理 2 条普通角色和 1 条个人权限')
    expect(wrapper.get('select[aria-label="选择新的内置权限职位"]').text()).toContain('生产文员')
    expect(wrapper.text()).not.toContain('调整原因')

    await wrapper
      .get('select[aria-label="选择新的内置权限职位"]')
      .setValue('position-production-clerk')
    await flushPromises()

    const previewButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('预览职位调整'))
    expect(previewButton).toBeDefined()
    expect(previewButton!.attributes('disabled')).toBeUndefined()
    await previewButton!.trigger('click')
    await flushPromises()

    expect(previewUserSystemPositionMock).toHaveBeenCalledWith('user-1', {
      base_revision: 2,
      system_position_role_id: 'position-production-clerk',
    })
    expect(wrapper.text()).toContain('清理历史角色')
    expect(wrapper.text()).toContain('清理个人特殊权限')
    expect(wrapper.text()).toContain('生产部（啤喷装） · 生产文员')

    const commitButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('确认并立即生效'))
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
    if (wrapper.findAll('[role="tab"]').some((t) => t.text() === '旧权限兼容'))
      await wrapper
        .findAll('[role="tab"]')
        .find((t) => t.text() === '旧权限兼容')!
        .trigger('mousedown', { button: 0 })

    const select = wrapper.get('select[aria-label="选择新的内置权限职位"]')
    expect((select.element as HTMLSelectElement).value).toBe('position-production-clerk')
    expect(getRoleAccessMock).toHaveBeenCalledWith('position-production-clerk')
  })

  it('allows cleanup while keeping the same system position', async () => {
    const wrapper = mountView()
    await flushPromises()
    if (wrapper.findAll('[role="tab"]').some((t) => t.text() === '旧权限兼容'))
      await wrapper
        .findAll('[role="tab"]')
        .find((t) => t.text() === '旧权限兼容')!
        .trigger('mousedown', { button: 0 })

    const cleanupButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('预览历史授权清理'))
    expect(cleanupButton).toBeDefined()
    expect(cleanupButton!.attributes('disabled')).toBeUndefined()

    await cleanupButton!.trigger('click')
    await flushPromises()

    expect(previewUserSystemPositionMock).toHaveBeenCalledWith('user-1', {
      base_revision: 2,
      system_position_role_id: 'position-engineer',
    })
  })

  it('shows a recommendation as a hint without automatically selecting or loading it', async () => {
    getUserAccessMock.mockResolvedValue({
      ...access,
      system_position_role_id: '',
      system_position_role_name: '',
      recommended_system_position_role_id: 'position-supervisor',
      legacy_role_count: 0,
      active_override_count: 0,
      cleanup_role_count: 0,
      cleanup_override_count: 0,
    })

    const wrapper = mountView()
    await flushPromises()
    if (wrapper.findAll('[role="tab"]').some((t) => t.text() === '旧权限兼容'))
      await wrapper
        .findAll('[role="tab"]')
        .find((t) => t.text() === '旧权限兼容')!
        .trigger('mousedown', { button: 0 })

    const select = wrapper.get('select[aria-label="选择新的内置权限职位"]')
    expect((select.element as HTMLSelectElement).value).toBe('')
    expect(select.text()).toContain('工程部主管（1 项权限） · 推荐')
    expect(wrapper.get('[data-testid="recommended-position-hint"]').text()).toContain(
      '推荐仅用于提示，不会自动选中或授权',
    )
    expect(getRoleAccessMock).not.toHaveBeenCalled()
    expect(
      wrapper
        .get('[data-testid="system-position-action-panel"]')
        .findAll('button')[1]
        .attributes('disabled'),
    ).toBeDefined()
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
    if (wrapper.findAll('[role="tab"]').some((t) => t.text() === '旧权限兼容'))
      await wrapper
        .findAll('[role="tab"]')
        .find((t) => t.text() === '旧权限兼容')!
        .trigger('mousedown', { button: 0 })

    expect(wrapper.get('[data-testid="missing-primary-department"]').text()).toContain(
      '尚未确认主组织资料',
    )
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
    if (wrapper.findAll('[role="tab"]').some((t) => t.text() === '旧权限兼容'))
      await wrapper
        .findAll('[role="tab"]')
        .find((t) => t.text() === '旧权限兼容')!
        .trigger('mousedown', { button: 0 })

    expect(wrapper.get('[data-testid="missing-primary-department"]').text()).toContain(
      '补全厂区和部门',
    )
    expect(wrapper.find('select[aria-label="选择新的内置权限职位"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="system-position-action-panel"]').exists()).toBe(false)
    expect(getRoleAccessMock).not.toHaveBeenCalled()
  })

  it('ignores a stale permission preview when role detail responses arrive out of order', async () => {
    const supervisorResponse = deferred<Record<string, unknown>>()
    const productionResponse = deferred<Record<string, unknown>>()
    getRoleAccessMock.mockImplementation((roleId: string) => {
      const role = positions.find((position) => position.id === roleId)
      if (roleId === 'position-supervisor') return supervisorResponse.promise
      if (roleId === 'position-production-clerk') return productionResponse.promise
      return Promise.resolve({
        ...role,
        permission_codes: ['molding_sample:manager_review'],
      })
    })

    const wrapper = mountView()
    await flushPromises()
    if (wrapper.findAll('[role="tab"]').some((t) => t.text() === '旧权限兼容'))
      await wrapper
        .findAll('[role="tab"]')
        .find((t) => t.text() === '旧权限兼容')!
        .trigger('mousedown', { button: 0 })
    const select = wrapper.get('select[aria-label="选择新的内置权限职位"]')

    await select.setValue('position-supervisor')
    await select.setValue('position-production-clerk')
    const pendingPreviewButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('预览职位调整'))
    expect(pendingPreviewButton?.attributes('disabled')).toBeDefined()

    productionResponse.resolve({
      ...positions.find((position) => position.id === 'position-production-clerk'),
      permission_codes: [],
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="selected-position-fixed-metadata"]').text()).toContain(
      '代码固定',
    )
    expect(wrapper.text()).toContain('该内置职位固定为空权限')

    supervisorResponse.resolve({
      ...positions.find((position) => position.id === 'position-supervisor'),
      permission_codes: ['molding_sample:manager_review'],
    })
    await flushPromises()
    expect((select.element as HTMLSelectElement).value).toBe('position-production-clerk')
    expect(wrapper.text()).toContain('该内置职位固定为空权限')
    expect(wrapper.text()).not.toContain('啤办经理终审')
  })

  it('locks role selection during preview and ignores an obsolete preview response', async () => {
    const delayedPreview = deferred<Record<string, unknown>>()
    previewUserSystemPositionMock.mockReturnValueOnce(delayedPreview.promise)

    const wrapper = mountView()
    await flushPromises()
    if (wrapper.findAll('[role="tab"]').some((t) => t.text() === '旧权限兼容'))
      await wrapper
        .findAll('[role="tab"]')
        .find((t) => t.text() === '旧权限兼容')!
        .trigger('mousedown', { button: 0 })
    const select = wrapper.get('select[aria-label="选择新的内置权限职位"]')
    await select.setValue('position-supervisor')
    await flushPromises()

    const previewButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('预览职位调整'))
    await previewButton!.trigger('click')
    expect(select.attributes('disabled')).toBeDefined()

    // Simulate a programmatic selection change even though the real control is
    // locked, proving that a late response still cannot revive the old token.
    select.element.removeAttribute('disabled')
    await select.setValue('position-production-clerk')
    await flushPromises()

    delayedPreview.resolve({
      preview_token: 'obsolete-preview',
      base_revision: 2,
      before_role_ids: ['position-engineer'],
      before_role_names: ['工程师'],
      after_role_id: 'position-supervisor',
      after_role_name: '工程部主管',
      removed_role_count: 1,
      removed_override_count: 0,
      requires_approval: false,
      high_risk: false,
      diffs: [],
      expires_at: '2026-07-16T12:00:00Z',
    })
    await flushPromises()

    expect((select.element as HTMLSelectElement).value).toBe('position-production-clerk')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(commitUserSystemPositionMock).not.toHaveBeenCalled()
  })

  it('lets an administrator grant the scoped self-review permission to an individual sales user', async () => {
    getUserAccessMock.mockResolvedValue({
      ...access,
      profile: {
        ...access.profile,
        primary_department: 'sales-business',
      },
      system_position_role_id: '',
      system_position_role_name: '',
      recommended_system_position_role_id: '',
      legacy_role_count: 0,
      active_override_count: 0,
      cleanup_role_count: 0,
      cleanup_override_count: 0,
      effective_access: [],
    })
    listPermissionsMock.mockResolvedValue([permission, selfReviewPermission])

    const wrapper = mountView()
    await flushPromises()

    const card = wrapper.get('[data-testid="self-review-permission-card"]')
    expect(card.text()).toContain('个人特殊权限 · 本人报价自审')
    expect(card.text()).toContain('当前未授权')
    const previewButton = card
      .findAll('button')
      .find((button) => button.text().includes('预览授予权限'))
    expect(previewButton).toBeDefined()
    await previewButton!.trigger('click')
    await flushPromises()

    expect(previewUserAccessMock).toHaveBeenCalledWith('user-1', {
      base_revision: 2,
      reason: '管理员授予内部报价本人自审权限',
      overrides: [
        {
          permission_code: 'internal_quote:self_review',
          effect: 'allow',
          factory_id: 'huaxing',
          department: 'sales-business',
        },
      ],
    })
    const dialog = wrapper.get('[role="dialog"]')
    const confirmButton = dialog
      .findAll('button')
      .find((button) => button.text().includes('确认并立即生效'))
    expect(confirmButton?.attributes('disabled')).toBeDefined()
    await dialog.get('input[type="checkbox"]').setValue(true)
    await confirmButton!.trigger('click')
    await flushPromises()

    expect(commitUserAccessMock).toHaveBeenCalledWith('user-1', 'self-review-preview', true)
    expect(wrapper.text()).toContain('已授予本人报价自审权限，立即生效')
  })
  it.each(['v2', 'legacy'] as const)('uses the authorized %s response on direct entry instead of query or cached hints', async (mode) => {
    routeState.query.identity_mode = mode === 'v2' ? 'legacy' : 'v2'
    rememberIdentityMode('', 'user-1', mode === 'v2' ? 'legacy' : 'v2')
    getUserAccessMock.mockResolvedValue({ ...access, identity_mode: mode })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('[role="tab"]').find((t) => t.text() === '旧权限兼容')!
      .trigger('mousedown', { button: 0 })
    expect(knownIdentityMode('', 'user-1')).toBe(mode)
    expect(wrapper.text()).not.toContain('尚未核实此人员的任职模式')
    expect(wrapper.text().includes('该人员已使用正式任职')).toBe(mode === 'v2')
    expect(wrapper.find('select[aria-label="选择新的内置权限职位"]').exists()).toBe(mode === 'legacy')
    expect(getUserAccessMock).toHaveBeenCalledWith('user-1')
    expect(previewUserSystemPositionMock).not.toHaveBeenCalled()
    expect(commitUserSystemPositionMock).not.toHaveBeenCalled()
  })

  it('keeps an older server response unknown and ignores identity mode in the URL', async () => {
    routeState.query.identity_mode = 'v2'
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('[role="tab"]').find((t) => t.text() === '旧权限兼容')!
      .trigger('mousedown', { button: 0 })
    expect(knownIdentityMode('', 'user-1')).toBe('unknown')
    expect(wrapper.text()).toContain('尚未核实此人员的任职模式')
    expect(wrapper.find('select[aria-label="选择新的内置权限职位"]').exists()).toBe(true)
  })

  it('clears a previous target before resolving a new route and ignores the old response', async () => {
    const old = deferred<Record<string, unknown>>()
    const newer = deferred<Record<string, unknown>>()
    getUserAccessMock.mockReturnValueOnce(old.promise).mockReturnValueOnce(newer.promise)
    const wrapper = mountView()
    await flushPromises()
    routeState.params.userId = 'user-2'
    await flushPromises()
    newer.resolve({
      ...access,
      identity_mode: 'legacy',
      user: { ...access.user, id: 'user-2' },
      profile: { ...access.profile, position: '新人员职位' },
    })
    await flushPromises()
    old.resolve({ ...access, identity_mode: 'v2' })
    await flushPromises()
    expect(wrapper.get('[data-testid="identity-summary"]').text()).toContain('新人员职位')
    expect(wrapper.text()).not.toContain('实际职位：技术员')
    expect(knownIdentityMode('', 'user-2')).toBe('legacy')
    expect(knownIdentityMode('', 'user-1')).toBe('unknown')
    wrapper.unmount()
  })
  it('keeps the authoritative V2 guidance after a compatibility preview is rejected', async () => {
    previewUserSystemPositionMock.mockRejectedValue({
      response: {
        status: 409,
        data: { detail: { code: 'IDENTITY_CHANGE_REQUIRED', message: '请通过任职变更办理' } },
      },
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .findAll('[role="tab"]')
      .find((t) => t.text() === '旧权限兼容')!
      .trigger('mousedown', { button: 0 })
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('预览历史授权清理'))!
      .trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('请返回人员中心')
    expect(wrapper.find('select[aria-label="选择新的内置权限职位"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('clears loaded access and ignores the previous viewer response after an account switch', async () => {
    viewerState.id = 'viewer-a'
    const old = deferred<Record<string, unknown>>()
    const newer = deferred<Record<string, unknown>>()
    getUserAccessMock.mockReturnValueOnce(old.promise).mockReturnValueOnce(newer.promise)
    const wrapper = mountView()
    await flushPromises()
    viewerState.id = 'viewer-b'
    await flushPromises()
    expect(getUserAccessMock).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-testid="identity-summary"]').exists()).toBe(false)
    old.resolve({ ...access, identity_mode: 'v2' })
    await flushPromises()
    expect(knownIdentityMode('viewer-b', 'user-1')).toBe('unknown')
    expect(wrapper.find('[data-testid="identity-summary"]').exists()).toBe(false)
    newer.resolve({ ...access, identity_mode: 'legacy' })
    await flushPromises()
    expect(knownIdentityMode('viewer-b', 'user-1')).toBe('legacy')
    expect(wrapper.find('[data-testid="identity-summary"]').exists()).toBe(true)
    viewerState.id = 'viewer-c'
    getUserAccessMock.mockRejectedValue({ response: { status: 403 } })
    await flushPromises()
    expect(wrapper.find('[data-testid="identity-summary"]').exists()).toBe(false)
    expect(knownIdentityMode('viewer-c', 'user-1')).toBe('unknown')
  })
})

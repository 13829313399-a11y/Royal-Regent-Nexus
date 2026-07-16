import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import IamRoleTemplatesView from '../IamRoleTemplatesView.vue'

const listSystemPositionsMock = vi.hoisted(() => vi.fn())
const listPermissionsMock = vi.hoisted(() => vi.fn())
const getManageableScopesMock = vi.hoisted(() => vi.fn())
const getRoleAccessMock = vi.hoisted(() => vi.fn())
const previewRoleAccessMock = vi.hoisted(() => vi.fn())
const commitRoleAccessMock = vi.hoisted(() => vi.fn())
const refreshSessionMock = vi.hoisted(() => vi.fn())

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ can: () => true, refreshSession: refreshSessionMock }),
}))

vi.mock('@/api/iam', () => ({
  iamApi: {
    listSystemPositions: listSystemPositionsMock,
    listPermissions: listPermissionsMock,
    getManageableScopes: getManageableScopesMock,
    getRoleAccess: getRoleAccessMock,
    previewRoleAccess: previewRoleAccessMock,
    commitRoleAccess: commitRoleAccessMock,
  },
}))

const role = {
  id: 'position-engineer', code: 'position_engineering_engineer', name: '工程师',
  description: '工程部基础权限', version: 1, is_protected: false, binding_count: 4,
  permission_count: 0, applicable_departments: ['engineering'], requires_global_factory: false,
  scope_guidance: '工程部', is_system_position: true, position_department: 'engineering',
  position_department_name: '工程部', position_sort_order: 220,
}

const permission = {
  code: 'molding_sample:read', name: '查看啤办单据', description: '',
  module_code: 'molding_sample', module_name: '啤办管理', action: 'read', risk_level: 'normal',
  scope_type: 'factory_department', status: 'active', sort_order: 1,
  applicable_departments: ['engineering'], requires_global_factory: false, scope_guidance: '本部门',
}

const businessPermission = {
  ...permission,
  code: 'customer_price:read', name: '查看报价中心', module_code: 'customer_price',
  module_name: '客户报价', action: 'read', sort_order: 2,
}

const supervisorRole = {
  ...role,
  id: 'position-engineering-supervisor', code: 'position_engineering_supervisor', name: '主管',
  description: '工程部审批权限', position_sort_order: 210,
}

const managerRole = {
  ...role,
  id: 'position-engineering-manager', code: 'position_engineering_manager', name: '经理',
  description: '工程部管理权限', position_sort_order: 200,
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise })
  return { promise, resolve }
}

function mountView() {
  return mount(IamRoleTemplatesView, {
    global: { stubs: { IamNavigation: { template: '<header />' } } },
  })
}

describe('IamRoleTemplatesView fixed position permissions', () => {
  beforeEach(() => {
    listSystemPositionsMock.mockReset()
      .mockResolvedValueOnce([role])
      .mockResolvedValueOnce([{ ...role, permission_count: 1, version: 2 }])
    listPermissionsMock.mockReset().mockResolvedValue([permission])
    getManageableScopesMock.mockReset().mockResolvedValue({
      is_super_admin: true, can_manage_role_templates: true,
      can_review_access_requests: true, scopes: [],
    })
    getRoleAccessMock.mockReset()
      .mockResolvedValueOnce({ ...role, permission_codes: [] })
      .mockResolvedValueOnce({ ...role, version: 2, permission_count: 1, permission_codes: ['molding_sample:read'] })
    previewRoleAccessMock.mockReset().mockResolvedValue({
      preview_token: 'role-preview-1', base_version: 1,
      diffs: [{ permission_code: 'molding_sample:read', before: false, after: true, risk_level: 'normal' }],
      affected_user_count: 4, high_risk: false,
    })
    commitRoleAccessMock.mockReset().mockResolvedValue({
      status: 'committed', authorization_version: 2,
    })
    refreshSessionMock.mockReset().mockResolvedValue(undefined)
  })

  it('refreshes the system-position summary count after a template commit', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('权限待配置')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('input[placeholder="说明为什么调整此内置职位权限"]').setValue('补充工程查看权限')
    await wrapper.findAll('button').find((button) => button.text().includes('预览职位影响'))!.trigger('click')
    await flushPromises()
    expect(previewRoleAccessMock).toHaveBeenCalledWith('position-engineer', {
      base_version: 1,
      reason: '补充工程查看权限',
      permission_codes: ['molding_sample:read'],
    })
    await wrapper.findAll('button').find((button) => button.text().includes('确认提交'))!.trigger('click')
    await flushPromises()

    expect(commitRoleAccessMock).toHaveBeenCalledWith('position-engineer', 'role-preview-1', false)
    expect(listSystemPositionsMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('已配置 1 项权限')
    expect(wrapper.text()).toContain('权限已更新')
  })

  it('keeps hidden selections in the full preview payload while filtering permissions', async () => {
    listPermissionsMock.mockReset().mockResolvedValue([permission, businessPermission])
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[aria-label*="molding_sample:read"]').setValue(true)
    await wrapper.get('input[placeholder="权限名称、模块或代码"]').setValue('客户报价')

    expect(wrapper.find('input[aria-label*="molding_sample:read"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('查看报价中心')
    expect(wrapper.text()).toContain('显示 1 / 2 项权限，当前已选择 1 项')

    await wrapper.get('input[placeholder="说明为什么调整此内置职位权限"]').setValue('补充工程查看权限')
    await wrapper.findAll('button').find((button) => button.text().includes('预览职位影响'))!.trigger('click')
    await flushPromises()

    expect(previewRoleAccessMock).toHaveBeenCalledWith('position-engineer', {
      base_version: 1,
      reason: '补充工程查看权限',
      permission_codes: ['molding_sample:read'],
    })
  })

  it('asks before discarding unsaved changes when switching positions', async () => {
    listSystemPositionsMock.mockReset().mockResolvedValue([role, supervisorRole])
    getRoleAccessMock.mockReset()
      .mockResolvedValueOnce({ ...role, permission_codes: [] })
      .mockResolvedValueOnce({ ...supervisorRole, permission_codes: [] })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[type="checkbox"]').setValue(true)
    const supervisorButton = wrapper.findAll('button').find((button) => button.text().includes('主管'))!
    await supervisorButton.trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(getRoleAccessMock).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-testid="role-editor-panel"] h2').text()).toBe('工程师')

    await supervisorButton.trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalledTimes(2)
    expect(getRoleAccessMock).toHaveBeenLastCalledWith('position-engineering-supervisor')
    expect(wrapper.get('[data-testid="role-editor-panel"] h2').text()).toBe('主管')
    confirmSpy.mockRestore()
  })

  it('ignores an older role response after a faster later switch', async () => {
    const supervisorResponse = deferred<typeof supervisorRole & { permission_codes: string[] }>()
    const managerResponse = deferred<typeof managerRole & { permission_codes: string[] }>()
    listSystemPositionsMock.mockReset().mockResolvedValue([role, supervisorRole, managerRole])
    getRoleAccessMock.mockReset()
      .mockResolvedValueOnce({ ...role, permission_codes: [] })
      .mockImplementationOnce(() => supervisorResponse.promise)
      .mockImplementationOnce(() => managerResponse.promise)
    const wrapper = mountView()
    await flushPromises()

    const supervisorButton = wrapper.findAll('button').find((button) => button.text().includes('主管'))!
    const managerButton = wrapper.findAll('button').find((button) => button.text().includes('经理'))!
    await supervisorButton.trigger('click')
    await managerButton.trigger('click')

    managerResponse.resolve({ ...managerRole, permission_codes: [] })
    await flushPromises()
    expect(wrapper.get('[data-testid="role-editor-panel"] h2').text()).toBe('经理')

    supervisorResponse.resolve({ ...supervisorRole, permission_codes: [] })
    await flushPromises()
    expect(wrapper.get('[data-testid="role-editor-panel"] h2').text()).toBe('经理')
  })

  it('freezes role and permission editing while a preview request is pending', async () => {
    const pendingPreview = deferred<{
      preview_token: string
      base_version: number
      diffs: Array<{ permission_code: string; before: boolean; after: boolean; risk_level: string }>
      affected_user_count: number
      high_risk: boolean
    }>()
    listSystemPositionsMock.mockReset().mockResolvedValue([role, supervisorRole])
    getRoleAccessMock.mockReset().mockResolvedValue({ ...role, permission_codes: [] })
    previewRoleAccessMock.mockReset().mockImplementationOnce(() => pendingPreview.promise)
    const wrapper = mountView()
    await flushPromises()

    const permissionCheckbox = wrapper.get('input[type="checkbox"]')
    const supervisorButton = wrapper.findAll('button').find((button) => button.text().includes('主管'))!
    await permissionCheckbox.setValue(true)
    await wrapper.get('input[placeholder="说明为什么调整此内置职位权限"]').setValue('补充工程查看权限')
    await wrapper.findAll('button').find((button) => button.text().includes('预览职位影响'))!.trigger('click')

    expect(permissionCheckbox.attributes('disabled')).toBeDefined()
    expect(supervisorButton.attributes('disabled')).toBeDefined()
    await supervisorButton.trigger('click')
    expect(getRoleAccessMock).toHaveBeenCalledTimes(1)

    pendingPreview.resolve({
      preview_token: 'role-preview-pending', base_version: 1,
      diffs: [{ permission_code: 'molding_sample:read', before: false, after: true, risk_level: 'normal' }],
      affected_user_count: 4, high_risk: false,
    })
    await flushPromises()

    expect(wrapper.text()).toContain('内置职位影响预览')
    expect(wrapper.get('[data-testid="role-editor-panel"] h2').text()).toBe('工程师')
  })
})

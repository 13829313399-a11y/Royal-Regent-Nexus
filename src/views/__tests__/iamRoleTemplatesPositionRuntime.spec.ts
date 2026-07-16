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
    const wrapper = mount(IamRoleTemplatesView, {
      global: { stubs: { IamNavigation: { template: '<header />' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('权限待配置')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('input[placeholder="说明为什么调整此内置职位权限"]').setValue('补充工程查看权限')
    await wrapper.findAll('button').find((button) => button.text().includes('预览职位影响'))!.trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('确认提交'))!.trigger('click')
    await flushPromises()

    expect(commitRoleAccessMock).toHaveBeenCalledWith('position-engineer', 'role-preview-1', false)
    expect(listSystemPositionsMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('已配置 1 项权限')
    expect(wrapper.text()).toContain('权限已更新')
  })
})

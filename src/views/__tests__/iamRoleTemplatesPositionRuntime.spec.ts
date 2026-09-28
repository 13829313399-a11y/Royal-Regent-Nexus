import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import IamRoleTemplatesView from '../IamRoleTemplatesView.vue'

enableAutoUnmount(afterEach)

const listSystemPositionsMock = vi.hoisted(() => vi.fn())
const listPermissionsMock = vi.hoisted(() => vi.fn())
const getRoleAccessMock = vi.hoisted(() => vi.fn())
const canMock = vi.hoisted(() => vi.fn())

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ can: canMock }),
}))

vi.mock('@/api/iam', () => ({
  iamApi: {
    listSystemPositions: listSystemPositionsMock,
    listPermissions: listPermissionsMock,
    getRoleAccess: getRoleAccessMock,
  },
}))

const engineerRole = {
  id: 'position_engineering_engineer',
  code: 'position_engineering_engineer',
  name: '工程师',
  description: '工程部基础权限',
  version: 4,
  is_protected: false,
  binding_count: 4,
  permission_count: 2,
  scope_mode: 'own_factory',
  applicable_departments: ['engineering'],
  requires_global_factory: false,
  scope_guidance: '工程部',
  is_system_position: true,
  is_editable: false,
  source: 'code',
  scope_mode_locked: true,
  definition_version: 'system-positions-v1',
  definition_hash: 'engineer-definition-hash',
  position_department: 'engineering',
  position_department_name: '工程部',
  position_sort_order: 220,
}

const generalManagerRole = {
  ...engineerRole,
  id: 'position_general_manager',
  code: 'position_general_manager',
  name: '总经理',
  description: '集团全业务管理',
  permission_count: 2,
  scope_mode: 'cross_factory_operate',
  definition_hash: 'general-manager-definition-hash',
  position_department: 'management',
  position_department_name: '总务',
  position_sort_order: 100,
}

const readPermission = {
  code: 'molding_sample:read',
  name: '查看啤办单据',
  description: '查看啤办业务单据。',
  module_code: 'molding_sample',
  module_name: '啤办管理',
  action: 'read',
  access_kind: 'read',
  risk_level: 'normal',
  scope_type: 'factory_department',
  status: 'active',
  sort_order: 1,
  applicable_departments: ['engineering'],
  requires_global_factory: false,
  scope_guidance: '业务部门',
}

const operationPermission = {
  ...readPermission,
  code: 'molding_sample:create',
  name: '新建啤办申请',
  action: 'create',
  access_kind: 'operate',
  risk_level: 'high',
  sort_order: 2,
}

const formerlyHiddenInactivePermission = {
  ...readPermission,
  code: 'system:access_approve',
  name: 'system:access_approve',
  description: '审批权限申请。',
  module_code: 'system',
  module_name: '系统管理',
  action: 'access_approve',
  access_kind: 'operate',
  risk_level: 'high',
  status: 'inactive',
  sort_order: 3,
}

function roleAccess(
  role = engineerRole,
  permissionCodes = ['molding_sample:read', 'system:access_approve'],
) {
  return { ...role, permission_codes: permissionCodes }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function mountView() {
  return mount(IamRoleTemplatesView, {
    global: {
      stubs: {
        teleport: { template: '<div><slot /></div>' },
        IamNavigation: {
          props: ['title', 'subtitle', 'compact'],
          template: '<header>{{ title }} · {{ subtitle }}</header>',
        },
      },
    },
  })
}

describe('IamRoleTemplatesView fixed position viewer', () => {
  beforeEach(() => {
    canMock.mockReset().mockReturnValue(true)
    listSystemPositionsMock.mockReset().mockResolvedValue([generalManagerRole, engineerRole])
    listPermissionsMock
      .mockReset()
      .mockResolvedValue([readPermission, operationPermission, formerlyHiddenInactivePermission])
    getRoleAccessMock
      .mockReset()
      .mockImplementation(async (roleId: string) =>
        roleId === generalManagerRole.id
          ? roleAccess(generalManagerRole, ['molding_sample:read', 'molding_sample:create'])
          : roleAccess(),
      )
  })

  it('keeps the page available without requesting the protected catalog when read permission is denied', async () => {
    canMock.mockReturnValue(false)

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-testid="role-catalog-protected-notice"]').text()).toContain(
      '权限目录受保护',
    )
    expect(wrapper.text()).toContain('此页面本身没有在线修改入口')
    expect(listSystemPositionsMock).not.toHaveBeenCalled()
    expect(listPermissionsMock).not.toHaveBeenCalled()
    expect(getRoleAccessMock).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="role-viewer-workspace"]').exists()).toBe(false)
  })

  it('loads the complete catalog and renders fixed metadata without any edit control', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(listPermissionsMock).toHaveBeenCalledWith('all')
    expect(wrapper.get('[data-testid="role-summary-panel"]').text()).toContain('代码固定 · 只读')
    expect(wrapper.get('[data-testid="fixed-role-metadata"]').text()).toContain(
      'system-positions-v1',
    )
    expect(wrapper.get('[data-testid="fixed-role-metadata"]').text()).not.toContain(
      'general-manager-definition-hash',
    )

    const summary = wrapper.get('[data-testid="role-summary-panel"]')
    const toolbar = wrapper.get('[data-testid="permission-filter-toolbar"]')
    const permissionList = wrapper.get('[data-testid="role-permission-scroll-region"]')
    expect(
      summary.element.compareDocumentPosition(toolbar.element) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(
      toolbar.element.compareDocumentPosition(permissionList.element) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(summary.find('[data-testid="permission-filter-toolbar"]').exists()).toBe(false)

    await wrapper.get('[data-testid="definition-details-trigger"]').trigger('click')
    const definitionPanel = wrapper.get('[data-testid="definition-details-panel"]')
    expect(definitionPanel.text()).toContain(
      '内置职位由系统代码固定维护；管理员可以查看，但不能在线修改。',
    )
    expect(definitionPanel.text()).toContain('general-manager-definition-hash')
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)
    expect(wrapper.find('input[type="radio"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('变更原因')
    expect(wrapper.text()).not.toContain('预览职位影响')
    expect(wrapper.text()).not.toContain('确认提交')
  })

  it('shows active, inactive, risk, scope, and inclusion state without hiding legacy IAM codes', async () => {
    listSystemPositionsMock.mockResolvedValue([engineerRole])
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).not.toContain('molding_sample:create')
    const allButton = wrapper
      .findAll('button')
      .find((button) => button.text().startsWith('全部权限'))!
    await allButton.trigger('click')
    for (const button of wrapper.findAll('button').filter((b) => b.text() === '说明与权限代码'))
      await button.trigger('click')
    expect(wrapper.text()).toContain('system:access_approve')
    expect(wrapper.text()).toContain('审批权限申请')
    expect(wrapper.text()).toContain('当前未启用')
    expect(wrapper.text()).toContain('高风险')
    expect(wrapper.text()).toContain('本厂查看')
    expect(wrapper.text()).toContain('已包含')
    expect(wrapper.text()).toContain('未包含')

    const configuredButton = wrapper
      .findAll('button')
      .find((button) => button.text().startsWith('已包含'))!
    await configuredButton.trigger('click')
    expect(wrapper.text()).toContain('molding_sample:read')
    expect(wrapper.text()).toContain('system:access_approve')
    expect(wrapper.text()).not.toContain('molding_sample:create')
  })

  it('keeps search and module filters in the read-only catalog', async () => {
    listSystemPositionsMock.mockResolvedValue([engineerRole])
    const wrapper = mountView()
    await flushPromises()

    const searchInput = wrapper.get('input[placeholder="搜索权限名称、模块或代码"]')
    await searchInput.setValue('客户不存在')
    expect(wrapper.text()).toContain('没有找到匹配的权限')
    await wrapper
      .findAll('button')
      .find((button) => button.text().startsWith('全部权限'))!
      .trigger('click')
    await searchInput.setValue('新建啤办')
    for (const button of wrapper
      .findAll('button')
      .filter((b) => b.text() === '说明与权限代码' && b.attributes('data-state') !== 'open'))
      await button.trigger('click')
    expect(wrapper.text()).toContain('molding_sample:create')
    expect(wrapper.text()).not.toContain('system:access_approve')
  })

  it('shows the general-manager business boundary and cross-factory scope', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-testid="role-viewer-panel"] h2').text()).toBe('总经理')
    const boundary = wrapper.get('[data-testid="general-manager-boundary"]').text()
    expect(boundary).toContain('跨厂操作 · 全业务部门')
    expect(boundary).toContain('不包含账号与权限管理')
    expect(wrapper.text()).toContain('跨厂操作')
  })

  it('copies the definition hash and closes the details panel with Escape', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="definition-details-trigger"]').trigger('click')
    const copyButton = wrapper
      .get('[data-testid="definition-details-panel"]')
      .findAll('button')
      .find((button) => button.text().includes('复制'))!
    await copyButton.trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('general-manager-definition-hash')
    expect(wrapper.text()).toContain('已复制定义哈希')

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(wrapper.find('[data-testid="definition-details-panel"]').exists()).toBe(false)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined })
  })

  it('surfaces a configured permission missing from the catalog as an error card', async () => {
    listSystemPositionsMock.mockResolvedValue([engineerRole])
    getRoleAccessMock.mockResolvedValue(roleAccess(engineerRole, ['missing_module:operate']))
    const wrapper = mountView()
    await flushPromises()

    await wrapper
      .findAll('button')
      .find((b) => b.text() === '说明与权限代码')!
      .trigger('click')
    expect(wrapper.text()).toContain('missing_module:operate')
    expect(wrapper.text()).toContain('定义异常：权限目录缺失')
  })

  it('ignores an older role response after a faster later switch', async () => {
    const engineerResponse = deferred<ReturnType<typeof roleAccess>>()
    const managerResponse = deferred<ReturnType<typeof roleAccess>>()
    getRoleAccessMock
      .mockReset()
      .mockResolvedValueOnce(roleAccess(generalManagerRole, ['molding_sample:read']))
      .mockImplementationOnce(() => engineerResponse.promise)
      .mockImplementationOnce(() => managerResponse.promise)
    const managerRole = {
      ...engineerRole,
      id: 'position_engineering_manager',
      name: '经理',
      position_sort_order: 200,
    }
    listSystemPositionsMock.mockResolvedValue([generalManagerRole, engineerRole, managerRole])
    const wrapper = mountView()
    await flushPromises()

    const engineerButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('工程师'))!
    const managerButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('经理') && !button.text().includes('总经理'))!
    await engineerButton.trigger('click')
    await managerButton.trigger('click')

    managerResponse.resolve(roleAccess(managerRole, []))
    await flushPromises()
    expect(wrapper.get('[data-testid="role-viewer-panel"] h2').text()).toBe('经理')

    engineerResponse.resolve(roleAccess(engineerRole, []))
    await flushPromises()
    expect(wrapper.get('[data-testid="role-viewer-panel"] h2').text()).toBe('经理')
  })
})

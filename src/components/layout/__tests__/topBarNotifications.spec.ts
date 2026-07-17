import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TopBar from '../TopBar.vue'
import { useAuthStore } from '@/stores/auth'
import type { AuthEffectiveAccess, AuthGrantScopeMode, AuthzMode } from '@/api/auth'
import { moldingSampleApi } from '@/api/moldingSample'
import type { MoldingSampleNotificationResponse } from '@/api/moldingSample'
import { systemApi, type SystemNotificationResponse } from '@/api/system'

const routeState = vi.hoisted(() => ({
  path: '/modules/production',
  name: 'module-center',
}))

const moldingSampleApiMock = vi.hoisted(() => ({
  listNotifications: vi.fn(),
  updateNotification: vi.fn(),
}))

const systemApiMock = vi.hoisted(() => ({
  listNotifications: vi.fn(),
  updateNotification: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({
    replace: vi.fn(),
  }),
}))

vi.mock('@/api/moldingSample', () => ({
  moldingSampleApi: moldingSampleApiMock,
}))

vi.mock('@/api/system', () => ({
  systemApi: systemApiMock,
}))

function createNotification(
  input: Partial<MoldingSampleNotificationResponse> & Pick<MoldingSampleNotificationResponse, 'id' | 'order_id' | 'factory_id' | 'target_role' | 'title'>,
): MoldingSampleNotificationResponse {
  return {
    target_module: 'engineering_molding_sample',
    event_type: '生产完成回传',
    message: `${input.title} 的消息内容`,
    from_status: '生产中',
    to_status: '已完成',
    status: '未读',
    actor_name: '系统',
    read_at: '',
    handled_at: '',
    created_at: '2026-07-06 15:00',
    ...input,
  }
}

function createSystemNotification(input: Partial<SystemNotificationResponse> & Pick<SystemNotificationResponse, 'id' | 'title'>): SystemNotificationResponse {
  return {
    target_user_id: '',
    target_permission: 'system:user_manage',
    target_factory_id: 'huaxing',
    type: 'user_registration',
    message: `${input.title} 的系统消息`,
    payload: { registration_request_id: 'registration-1' },
    status: 'unread',
    created_at: '2026-07-08 19:00',
    read_at: '',
    handled_at: '',
    ...input,
  }
}

function seedAccount(options: {
  roles: string[]
  permissions?: string[]
  factoryScopes?: string[]
  authzMode?: AuthzMode
  effectiveAccess?: AuthEffectiveAccess[]
  roleId?: string
  factoryId?: string
  department?: string
  scopeMode?: AuthGrantScopeMode
  readPermissionCodes?: string[]
  unrestrictedDepartment?: boolean
}) {
  const permissions = options.permissions ?? ['molding_sample:notification_read']
  const factoryScopes = options.factoryScopes ?? ['huaxing']
  const administrator = options.roles.includes('系统管理员')
  const roleId = options.roleId ?? (administrator ? 'admin' : 'test-role')
  const department = options.department ?? (administrator ? 'system' : 'engineering')
  useAuthStore().applySession({
    id: 'user-test',
    username: 'tester',
    display_name: '华兴工程师',
    roles: options.roles,
    permissions,
    grants: [{
      role_id: roleId,
      role_code: roleId,
      role_name: options.roles[0] ?? '测试角色',
      factory_id: options.factoryId ?? (factoryScopes.includes('*') ? '*' : factoryScopes[0] ?? 'huaxing'),
      department,
      permissions,
      scope_mode: options.scopeMode,
      read_permission_codes: options.readPermissionCodes,
      unrestricted_department: options.unrestrictedDepartment,
      data_scope: administrator ? 'all' : 'department',
    }],
    factory_scopes: factoryScopes,
    department_scopes: [department],
    authz_mode: options.authzMode,
    effective_access: options.effectiveAccess,
    force_password_change: false,
  })
}

function mountTopBar() {
  return mount(TopBar, {
    global: {
      stubs: {
        AccountMenu: { template: '<div data-testid="account-menu-stub" />' },
        RouteLoadingBar: { template: '<div data-testid="route-loading-stub" />' },
        RouterLink: {
          props: ['to'],
          template: '<a :href="typeof to === `string` ? to : `#`"><slot /></a>',
        },
      },
    },
  })
}

describe('TopBar notifications', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    moldingSampleApiMock.listNotifications.mockResolvedValue([])
    moldingSampleApiMock.updateNotification.mockResolvedValue({})
    systemApiMock.listNotifications.mockResolvedValue([])
    systemApiMock.updateNotification.mockResolvedValue({})
  })

  it('shows only unhandled notifications assigned to the current account role and factory', async () => {
    seedAccount({ roles: ['工程师'] })
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createNotification({
        id: 'N-ENGINEER-1',
        order_id: 'BP-ENGINEER-1',
        factory_id: 'huaxing',
        target_role: '工程部',
        title: '华兴工程回传',
      }),
      createNotification({
        id: 'N-ENGINEER-2',
        order_id: 'BP-ENGINEER-2',
        factory_id: 'huaxing',
        target_role: '工程部',
        status: '已读',
        title: '华兴工程已读待处理',
      }),
      createNotification({
        id: 'N-PRODUCTION',
        order_id: 'BP-PRODUCTION',
        factory_id: 'huaxing',
        target_role: '啤机部',
        target_module: 'production_molding_sample_task',
        title: '啤机部任务',
      }),
      createNotification({
        id: 'N-OTHER-FACTORY',
        order_id: 'BP-OTHER-FACTORY',
        factory_id: 'huadeng',
        target_role: '工程部',
        title: '华登工程通知',
      }),
      createNotification({
        id: 'N-HANDLED',
        order_id: 'BP-HANDLED',
        factory_id: 'huaxing',
        target_role: '工程部',
        status: '已处理',
        title: '已处理工程通知',
      }),
    ])

    const wrapper = mountTopBar()
    await flushPromises()

    expect(moldingSampleApi.listNotifications).toHaveBeenCalledWith()
    expect(wrapper.get('button[aria-label="未处理项通知"]').text()).toContain('2')

    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')

    expect(wrapper.text()).toContain('未处理项通知')
    expect(wrapper.text()).toContain('华兴工程回传')
    expect(wrapper.text()).toContain('华兴工程已读待处理')
    expect(wrapper.text()).not.toContain('啤机部任务')
    expect(wrapper.text()).not.toContain('华登工程通知')
    expect(wrapper.text()).not.toContain('已处理工程通知')
  })

  it('filters same-factory notifications by their target department in enforce mode', async () => {
    seedAccount({
      roles: ['工程师'],
      authzMode: 'enforce',
      effectiveAccess: [{
        permission_code: 'molding_sample:notification_read',
        factory_id: 'huaxing',
        department: 'engineering',
        effect: 'allow',
        allowed: true,
        source_type: 'role',
        source_ids: ['engineering-role'],
      }],
    })
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createNotification({
        id: 'N-ENGINEERING-DEPARTMENT',
        order_id: 'BP-ENGINEERING-DEPARTMENT',
        factory_id: 'huaxing',
        target_department: 'engineering',
        target_role: '工程部',
        title: '工程部待办',
      }),
      createNotification({
        id: 'N-PRODUCTION-DEPARTMENT',
        order_id: 'BP-PRODUCTION-DEPARTMENT',
        factory_id: 'huaxing',
        target_department: 'production',
        target_role: '工程部',
        title: '生产部待办',
      }),
    ])

    const wrapper = mountTopBar()
    await flushPromises()

    expect(wrapper.get('button[aria-label="未处理项通知"]').text()).toContain('1')
    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    expect(wrapper.text()).toContain('工程部待办')
    expect(wrapper.text()).not.toContain('生产部待办')
  })

  it('maps legacy manager notifications to the management department', async () => {
    seedAccount({
      roles: ['经理'],
      authzMode: 'enforce',
      effectiveAccess: [{
        permission_code: 'molding_sample:notification_read',
        factory_id: 'huaxing',
        department: 'management',
        effect: 'allow',
        allowed: true,
        source_type: 'role',
        source_ids: ['manager-role'],
      }],
    })
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createNotification({
        id: 'N-MANAGER-LEGACY',
        order_id: 'BP-MANAGER-LEGACY',
        factory_id: 'huaxing',
        target_role: '经理',
        title: '经理审核待办',
      }),
    ])

    const wrapper = mountTopBar()
    await flushPromises()

    expect(wrapper.get('button[aria-label="未处理项通知"]').text()).toContain('1')
    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    expect(wrapper.text()).toContain('经理审核待办')
  })

  it('accepts the historical molding alias for production notifications', async () => {
    seedAccount({
      roles: ['啤机部文员'],
      authzMode: 'enforce',
      effectiveAccess: [{
        permission_code: 'molding_sample:notification_read',
        factory_id: 'huaxing',
        department: 'molding',
        effect: 'allow',
        allowed: true,
        source_type: 'role',
        source_ids: ['legacy-molding-role'],
      }],
    })
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createNotification({
        id: 'N-PRODUCTION-ALIAS',
        order_id: 'BP-PRODUCTION-ALIAS',
        factory_id: 'huaxing',
        target_department: 'production',
        target_role: '啤机部',
        target_module: 'production_molding_sample_task',
        title: '历史啤机部门待办',
      }),
    ])

    const wrapper = mountTopBar()
    await flushPromises()

    expect(wrapper.get('button[aria-label="未处理项通知"]').text()).toContain('1')
    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    expect(wrapper.text()).toContain('历史啤机部门待办')
  })

  it('shows production-task notifications for molding department accounts', async () => {
    seedAccount({
      roles: ['啤机部文员'],
      permissions: ['molding_sample:notification_read', 'molding_sample:production_read'],
      factoryScopes: ['huaxing'],
    })
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createNotification({
        id: 'N-PRODUCTION-1',
        order_id: 'BP-PRODUCTION-1',
        factory_id: 'huaxing',
        target_role: '啤机部',
        target_module: 'production_molding_sample_task',
        title: '待接单生产任务',
      }),
      createNotification({
        id: 'N-ENGINEERING-1',
        order_id: 'BP-ENGINEERING-1',
        factory_id: 'huaxing',
        target_role: '工程部',
        title: '工程部回传',
      }),
    ])

    const wrapper = mountTopBar()
    await flushPromises()

    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')

    expect(wrapper.text()).toContain('待接单生产任务')
    expect(wrapper.text()).not.toContain('工程部回传')
  })

  it('lets an engineering supervisor inherit same-department engineering notifications', async () => {
    seedAccount({
      roles: ['工程主管'],
      permissions: [
        'molding_sample:notification_read',
        'molding_sample:supervisor_review',
        'molding_sample:create',
      ],
      factoryScopes: ['huaxing'],
    })
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createNotification({
        id: 'N-SUPERVISOR-1',
        order_id: 'BP-SUPERVISOR-1',
        factory_id: 'huaxing',
        target_role: '工程主管',
        event_type: '待主管审核',
        title: '啤办单待主管审核',
      }),
      createNotification({
        id: 'N-ENGINEERING-DEPT-1',
        order_id: 'BP-ENGINEERING-DEPT-1',
        factory_id: 'huaxing',
        target_role: '工程部',
        title: '工程部回传',
      }),
    ])

    const wrapper = mountTopBar()
    await flushPromises()

    expect(wrapper.get('button[aria-label="未处理项通知"]').text()).toContain('2')

    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('啤办单待主管审核')
    expect(wrapper.text()).toContain('工程部回传')
  })

  it('keeps an engineering fixed position bell inside its home factory and department', async () => {
    seedAccount({
      roles: ['工程师'],
      permissions: ['molding_sample:notification_read', 'molding_sample:read'],
      factoryScopes: ['*'],
      roleId: 'position_engineering_engineer',
      factoryId: 'huaxing',
      department: 'engineering',
      scopeMode: 'cross_factory_read',
      readPermissionCodes: ['molding_sample:notification_read', 'molding_sample:read'],
      unrestrictedDepartment: true,
    })
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createNotification({
        id: 'N-ENGINEER-HOME',
        order_id: 'BP-ENGINEER-HOME',
        factory_id: 'huaxing',
        target_role: '工程部',
        title: '华兴工程通知',
      }),
      createNotification({
        id: 'N-ENGINEER-FOREIGN',
        order_id: 'BP-ENGINEER-FOREIGN',
        factory_id: 'huadeng',
        target_role: '工程部',
        title: '华登工程通知',
      }),
      createNotification({
        id: 'N-ENGINEER-PRODUCTION',
        order_id: 'BP-ENGINEER-PRODUCTION',
        factory_id: 'huaxing',
        target_role: '啤机部',
        target_module: 'production_molding_sample_task',
        title: '华兴啤机通知',
      }),
    ])

    const wrapper = mountTopBar()
    await flushPromises()

    expect(wrapper.get('button[aria-label="未处理项通知"]').text()).toContain('1')
    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    expect(wrapper.text()).toContain('华兴工程通知')
    expect(wrapper.text()).not.toContain('华登工程通知')
    expect(wrapper.text()).not.toContain('华兴啤机通知')
  })

  it('keeps a molding clerk bell local while a molding supervisor receives all factories', async () => {
    const notifications = [
      createNotification({
        id: 'N-MOLDING-HOME',
        order_id: 'BP-MOLDING-HOME',
        factory_id: 'huaxing',
        target_role: '啤机部',
        target_module: 'production_molding_sample_task',
        title: '华兴啤机任务',
      }),
      createNotification({
        id: 'N-MOLDING-FOREIGN',
        order_id: 'BP-MOLDING-FOREIGN',
        factory_id: 'huadeng',
        target_role: '啤机部',
        target_module: 'production_molding_sample_task',
        title: '华登啤机任务',
      }),
      createNotification({
        id: 'N-MOLDING-ENGINEERING',
        order_id: 'BP-MOLDING-ENGINEERING',
        factory_id: 'huaxing',
        target_role: '工程部',
        title: '华兴工程消息',
      }),
    ]
    const sharedOptions = {
      permissions: ['molding_sample:notification_read', 'molding_sample:production_read'],
      factoryScopes: ['*'],
      factoryId: 'huaxing',
      department: 'production',
      readPermissionCodes: ['molding_sample:notification_read', 'molding_sample:production_read'],
      unrestrictedDepartment: true,
    }

    seedAccount({
      ...sharedOptions,
      roles: ['啤机文员'],
      roleId: 'position_molding_clerk',
      scopeMode: 'cross_factory_read',
    })
    moldingSampleApiMock.listNotifications.mockResolvedValue(notifications)
    const clerkWrapper = mountTopBar()
    await flushPromises()
    expect(clerkWrapper.get('button[aria-label="未处理项通知"]').text()).toContain('1')
    await clerkWrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    expect(clerkWrapper.text()).toContain('华兴啤机任务')
    expect(clerkWrapper.text()).not.toContain('华登啤机任务')
    expect(clerkWrapper.text()).not.toContain('华兴工程消息')
    clerkWrapper.unmount()

    seedAccount({
      ...sharedOptions,
      roles: ['啤机主管'],
      roleId: 'position_molding_supervisor',
      scopeMode: 'cross_factory_operate',
    })
    const supervisorWrapper = mountTopBar()
    await flushPromises()
    expect(supervisorWrapper.get('button[aria-label="未处理项通知"]').text()).toContain('2')
    await supervisorWrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    expect(supervisorWrapper.text()).toContain('华兴啤机任务')
    expect(supervisorWrapper.text()).toContain('华登啤机任务')
    expect(supervisorWrapper.text()).not.toContain('华兴工程消息')
  })

  it('reloads notifications when opening the panel and links messages to their workflow page', async () => {
    seedAccount({ roles: ['工程师'] })
    moldingSampleApiMock.listNotifications
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        createNotification({
          id: 'N-ENGINEERING-ROUTE',
          order_id: 'BP-ENGINEERING-ROUTE',
          factory_id: 'huaxing',
          target_role: '工程部',
          title: '啤办生产完成',
        }),
      ])

    const wrapper = mountTopBar()
    await flushPromises()

    expect(wrapper.get('button[aria-label="未处理项通知"]').text()).not.toContain('1')

    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    await flushPromises()

    expect(moldingSampleApi.listNotifications).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('啤办生产完成')
    const notificationLink = wrapper
      .findAll('a')
      .find((link) => link.attributes('href')?.includes('order_id=BP-ENGINEERING-ROUTE'))
    expect(notificationLink?.attributes('href')).toContain('/modules/molding-sample?factory=huaxing')
  })

  it('closes the notification panel when clicking outside or pressing Escape', async () => {
    seedAccount({ roles: ['工程师'] })
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createNotification({
        id: 'N-OUTSIDE-CLOSE',
        order_id: 'BP-OUTSIDE-CLOSE',
        factory_id: 'huaxing',
        target_role: '工程部',
        title: '点击外部关闭',
      }),
    ])

    const wrapper = mountTopBar()
    await flushPromises()

    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    expect(wrapper.find('[aria-label="未处理项通知面板"]').exists()).toBe(true)

    document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(wrapper.find('[aria-label="未处理项通知面板"]').exists()).toBe(false)

    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(wrapper.find('[aria-label="未处理项通知面板"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('pops a routed message when a supervisor receives a new review notification', async () => {
    seedAccount({
      roles: ['工程主管'],
      permissions: ['molding_sample:notification_read', 'molding_sample:supervisor_review'],
      factoryScopes: ['huaxing'],
    })
    moldingSampleApiMock.listNotifications
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        createNotification({
          id: 'N-SUPERVISOR-POPUP',
          order_id: 'BP-SUPERVISOR-POPUP',
          factory_id: 'huaxing',
          target_role: '工程主管',
          event_type: '待主管审核',
          title: '啤办单待主管审核',
        }),
      ])

    const wrapper = mountTopBar()
    await flushPromises()

    expect(wrapper.text()).not.toContain('新待办通知')

    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('新待办通知')
    expect(wrapper.text()).toContain('啤办单待主管审核')
    const toastLink = wrapper
      .findAll('a')
      .find((link) => link.attributes('href')?.includes('order_id=BP-SUPERVISOR-POPUP'))
    expect(toastLink?.attributes('href')).toContain('/modules/molding-sample?factory=huaxing')
  })

  it('marks a clicked notification handled so it no longer stays visible', async () => {
    seedAccount({
      roles: ['工程主管'],
      permissions: ['molding_sample:notification_read', 'molding_sample:supervisor_review'],
      factoryScopes: ['huaxing'],
    })
    moldingSampleApiMock.listNotifications
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        createNotification({
          id: 'N-SUPERVISOR-HANDLED',
          order_id: 'BP-SUPERVISOR-HANDLED',
          factory_id: 'huaxing',
          target_role: '工程主管',
          event_type: '待主管审核',
          title: '啤办单待主管审核',
        }),
      ])

    const wrapper = mountTopBar()
    await flushPromises()

    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    await flushPromises()

    const toastLink = wrapper
      .findAll('a')
      .find((link) =>
        link.text().includes('新待办通知')
        && link.attributes('href')?.includes('order_id=BP-SUPERVISOR-HANDLED'),
      )
    expect(toastLink).toBeTruthy()

    await toastLink?.trigger('click')
    await flushPromises()

    expect(moldingSampleApi.updateNotification).toHaveBeenCalledWith('N-SUPERVISOR-HANDLED', { status: '已处理' })
    expect(wrapper.get('button[aria-label="未处理项通知"]').text()).not.toContain('1')
    expect(wrapper.text()).not.toContain('新待办通知')
  })

  it('polls notifications while the top bar is mounted', async () => {
    vi.useFakeTimers()
    try {
      seedAccount({ roles: ['工程师'] })
      moldingSampleApiMock.listNotifications.mockResolvedValue([])

      const wrapper = mountTopBar()
      await flushPromises()

      expect(moldingSampleApi.listNotifications).toHaveBeenCalledTimes(1)

      await vi.advanceTimersByTimeAsync(30_000)
      await flushPromises()

      expect(moldingSampleApi.listNotifications).toHaveBeenCalledTimes(2)
      wrapper.unmount()
    }
    finally {
      vi.useRealTimers()
    }
  })

  it('marks a clicked system registration notification read until approval handles it', async () => {
    seedAccount({
      roles: ['系统管理员'],
      permissions: ['system:user_manage'],
      factoryScopes: ['*'],
    })
    systemApiMock.listNotifications.mockResolvedValue([
      createSystemNotification({
        id: 'SYS-REG-1',
        title: '新用户注册待审批',
        message: '华兴 / 工程部 / 张三 申请开通账号',
      }),
    ])

    const wrapper = mountTopBar()
    await flushPromises()

    expect(systemApi.listNotifications).toHaveBeenCalledWith()
    expect(wrapper.get('button[aria-label="未处理项通知"]').text()).toContain('1')

    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('系统通知')
    expect(wrapper.text()).toContain('新用户注册待审批')
    const notificationLink = wrapper
      .findAll('a')
      .find((link) => link.attributes('href')?.includes('/system/users'))
    expect(notificationLink?.attributes('href')).toContain('request_id=registration-1')

    await notificationLink?.trigger('click')
    await flushPromises()

    expect(systemApi.updateNotification).toHaveBeenCalledWith('SYS-REG-1', { status: 'read' })
    expect(wrapper.get('button[aria-label="未处理项通知"]').text()).toContain('1')
  })
})

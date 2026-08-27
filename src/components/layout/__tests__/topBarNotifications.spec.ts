import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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

const mountedWrappers: Array<ReturnType<typeof mount>> = []

vi.mock('vue-router', () => ({
  RouterLink: {
    props: ['to'],
    template: '<a :href="typeof to === `string` ? to : `#`"><slot /></a>',
  },
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
  const wrapper = mount(TopBar, {
    attachTo: document.body,
    global: {
      stubs: {
        Teleport: true,
        AccountMenu: { template: '<div data-testid="account-menu-stub" />' },
        RouteLoadingBar: { template: '<div data-testid="route-loading-stub" />' },
        RouterLink: {
          props: ['to'],
          template: '<a :href="typeof to === `string` ? to : `#`"><slot /></a>',
        },
      },
    },
  })
  mountedWrappers.push(wrapper)
  return wrapper
}

describe('TopBar notifications', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    window.localStorage.clear()
    moldingSampleApiMock.listNotifications.mockResolvedValue([])
    moldingSampleApiMock.updateNotification.mockResolvedValue({})
    systemApiMock.listNotifications.mockResolvedValue([])
    systemApiMock.updateNotification.mockResolvedValue({})
  })

  afterEach(() => {
    mountedWrappers.splice(0).forEach((wrapper) => wrapper.unmount())
    vi.useRealTimers()
  })

  it('shows scoped notifications and keeps handled items out of the pending tab', async () => {
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
    expect(wrapper.get('button[aria-label^="通知中心"]').text()).toContain('1')

    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')

    expect(wrapper.text()).toContain('通知中心')
    expect(wrapper.text()).toContain('1 条未读 · 2 项待处理')
    expect(wrapper.text()).toContain('华兴工程回传')
    expect(wrapper.text()).toContain('华兴工程已读待处理')
    expect(wrapper.text()).not.toContain('啤机部任务')
    expect(wrapper.text()).not.toContain('华登工程通知')
    expect(wrapper.text()).toContain('已处理工程通知')

    const pendingTab = wrapper.findAll('button').find((button) => button.text().includes('待处理'))
    expect(pendingTab).toBeTruthy()
    await pendingTab?.trigger('click')
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

    expect(wrapper.get('button[aria-label^="通知中心"]').text()).toContain('1')
    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
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

    expect(wrapper.get('button[aria-label^="通知中心"]').text()).toContain('1')
    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
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

    expect(wrapper.get('button[aria-label^="通知中心"]').text()).toContain('1')
    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
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

    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')

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

    expect(wrapper.get('button[aria-label^="通知中心"]').text()).toContain('2')

    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
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

    expect(wrapper.get('button[aria-label^="通知中心"]').text()).toContain('1')
    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
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
    expect(clerkWrapper.get('button[aria-label^="通知中心"]').text()).toContain('1')
    await clerkWrapper.get('button[aria-label^="通知中心"]').trigger('click')
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
    expect(supervisorWrapper.get('button[aria-label^="通知中心"]').text()).toContain('2')
    await supervisorWrapper.get('button[aria-label^="通知中心"]').trigger('click')
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

    expect(wrapper.get('button[aria-label^="通知中心"]').text()).not.toContain('1')

    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
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

    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
    expect(wrapper.find('[role="dialog"][aria-labelledby="notification-center-title"]').exists()).toBe(true)

    document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(wrapper.find('[role="dialog"][aria-labelledby="notification-center-title"]').exists()).toBe(false)

    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(wrapper.find('[role="dialog"][aria-labelledby="notification-center-title"]').exists()).toBe(false)
    await new Promise((resolve) => window.setTimeout(resolve, 0))
    expect(document.activeElement).toBe(wrapper.get('button[aria-label^="通知中心"]').element)

    wrapper.unmount()
  })

  it('focuses the panel heading and supports ARIA tab keyboard navigation', async () => {
    seedAccount({ roles: ['工程师'] })

    const wrapper = mountTopBar()
    await flushPromises()

    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
    await flushPromises()

    const heading = wrapper.get('#notification-center-title')
    const tabpanel = wrapper.get('#notification-tabpanel')
    const allTab = wrapper.get('#notification-tab-all')
    expect(document.activeElement).toBe(heading.element)
    expect(tabpanel.attributes('role')).toBe('tabpanel')
    expect(allTab.attributes('aria-controls')).toBe('notification-tabpanel')
    expect(allTab.attributes('aria-selected')).toBe('true')
    expect(allTab.attributes('tabindex')).toBe('0')

    await allTab.trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()

    const pendingTab = wrapper.get('#notification-tab-pending')
    expect(pendingTab.attributes('aria-selected')).toBe('true')
    expect(pendingTab.attributes('tabindex')).toBe('0')
    expect(allTab.attributes('tabindex')).toBe('-1')
    expect(document.activeElement).toBe(pendingTab.element)

    await pendingTab.trigger('keydown', { key: 'End' })
    await flushPromises()

    const systemTab = wrapper.get('#notification-tab-system')
    expect(systemTab.attributes('aria-selected')).toBe('true')
    expect(systemTab.attributes('tabindex')).toBe('0')
    expect(document.activeElement).toBe(systemTab.element)

    await systemTab.trigger('keydown', { key: 'Home' })
    await flushPromises()

    expect(allTab.attributes('aria-selected')).toBe('true')
    expect(allTab.attributes('tabindex')).toBe('0')
    expect(document.activeElement).toBe(allTab.element)
  })

  it('pops a routed message when a supervisor receives a new review notification', async () => {
    vi.useFakeTimers()
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

    expect(wrapper.find('[role="status"]').exists()).toBe(false)

    await vi.advanceTimersByTimeAsync(25_000)
    await flushPromises()

    expect(wrapper.find('[role="status"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('啤办单待主管审核')
    const toastLink = wrapper
      .findAll('a')
      .find((link) => link.attributes('href')?.includes('order_id=BP-SUPERVISOR-POPUP'))
    expect(toastLink?.attributes('href')).toContain('/modules/molding-sample?factory=huaxing')

    await toastLink?.trigger('click')
    await flushPromises()
    expect(moldingSampleApi.updateNotification).toHaveBeenCalledWith('N-SUPERVISOR-POPUP', { status: '已读' })
    expect(moldingSampleApi.updateNotification).not.toHaveBeenCalledWith('N-SUPERVISOR-POPUP', { status: '已处理' })
  })

  it('closes a toast without changing notification state', async () => {
    vi.useFakeTimers()
    seedAccount({ roles: ['工程师'] })
    moldingSampleApiMock.listNotifications
      .mockResolvedValueOnce([])
      .mockResolvedValue([
        createNotification({
          id: 'N-DISMISS',
          order_id: 'BP-DISMISS',
          factory_id: 'huaxing',
          target_role: '工程部',
          title: '可关闭提醒',
        }),
      ])
    const wrapper = mountTopBar()
    await flushPromises()

    await vi.advanceTimersByTimeAsync(25_000)
    await flushPromises()
    expect(wrapper.find('[role="status"]').exists()).toBe(true)

    await wrapper.get('button[aria-label="关闭消息提醒"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(moldingSampleApi.updateNotification).not.toHaveBeenCalled()
    expect(systemApi.updateNotification).not.toHaveBeenCalled()
  })

  it('pauses the toast timeout while hovered and resumes afterward', async () => {
    vi.useFakeTimers()
    seedAccount({ roles: ['工程师'] })
    moldingSampleApiMock.listNotifications
      .mockResolvedValueOnce([])
      .mockResolvedValue([
        createNotification({
          id: 'N-PAUSE',
          order_id: 'BP-PAUSE',
          factory_id: 'huaxing',
          target_role: '工程部',
          title: '暂停倒计时提醒',
        }),
      ])
    const wrapper = mountTopBar()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(25_000)
    await flushPromises()

    const toast = wrapper.get('[role="status"]')
    await toast.trigger('mouseenter')
    await vi.advanceTimersByTimeAsync(12_000)
    expect(wrapper.find('[role="status"]').exists()).toBe(true)

    await toast.trigger('mouseleave')
    await vi.advanceTimersByTimeAsync(10_000)
    await flushPromises()
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('marks a clicked business notification read while leaving it pending', async () => {
    seedAccount({
      roles: ['工程主管'],
      permissions: ['molding_sample:notification_read', 'molding_sample:supervisor_review'],
      factoryScopes: ['huaxing'],
    })
    moldingSampleApiMock.listNotifications.mockResolvedValue([
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

    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
    await flushPromises()

    const notificationLink = wrapper
      .findAll('a')
      .find((link) => link.attributes('href')?.includes('order_id=BP-SUPERVISOR-HANDLED'))
    expect(notificationLink).toBeTruthy()

    await notificationLink?.trigger('click')
    await flushPromises()

    expect(moldingSampleApi.updateNotification).toHaveBeenCalledWith('N-SUPERVISOR-HANDLED', { status: '已读' })
    expect(wrapper.get('button[aria-label^="通知中心"]').text()).not.toContain('1')

    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('0 条未读 · 1 项待处理')
    expect(wrapper.text()).toContain('啤办单待主管审核')
  })

  it('polls notifications while the top bar is mounted', async () => {
    vi.useFakeTimers()
    try {
      seedAccount({ roles: ['工程师'] })
      moldingSampleApiMock.listNotifications.mockResolvedValue([])

      const wrapper = mountTopBar()
      await flushPromises()

      expect(moldingSampleApi.listNotifications).toHaveBeenCalledTimes(1)

      await vi.advanceTimersByTimeAsync(25_000)
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
    expect(wrapper.get('button[aria-label^="通知中心"]').text()).toContain('1')

    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
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
    expect(wrapper.get('button[aria-label^="通知中心"]').text()).not.toContain('1')

    await wrapper.get('button[aria-label^="通知中心"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('0 条未读 · 1 项待处理')
    expect(wrapper.text()).toContain('新用户注册待审批')
  })

})

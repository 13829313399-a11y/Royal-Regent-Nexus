import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TopBar from '../TopBar.vue'
import { useAuthStore } from '@/stores/auth'
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
}) {
  useAuthStore().applySession({
    id: 'user-test',
    username: 'tester',
    display_name: '华兴工程师',
    roles: options.roles,
    permissions: options.permissions ?? ['molding_sample:notification_read'],
    grants: [],
    factory_scopes: options.factoryScopes ?? ['huaxing'],
    department_scopes: ['engineering'],
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

  it('shows supervisor review notifications without mixing engineering department messages', async () => {
    seedAccount({
      roles: ['工程主管'],
      permissions: ['molding_sample:notification_read', 'molding_sample:supervisor_review'],
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

    expect(wrapper.get('button[aria-label="未处理项通知"]').text()).toContain('1')

    await wrapper.get('button[aria-label="未处理项通知"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('啤办单待主管审核')
    expect(wrapper.text()).not.toContain('工程部回传')
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

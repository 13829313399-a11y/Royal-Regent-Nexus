import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { formatNotificationTime, useNotificationCenter } from '@/composables/useNotificationCenter'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import type { MoldingSampleNotificationResponse } from '@/api/moldingSample'
import type { SystemNotificationResponse } from '@/api/system'

const moldingSampleApiMock = vi.hoisted(() => ({
  listNotifications: vi.fn(),
  updateNotification: vi.fn(),
}))

const systemApiMock = vi.hoisted(() => ({
  listNotifications: vi.fn(),
  updateNotification: vi.fn(),
}))

const soundMock = vi.hoisted(() => ({
  play: vi.fn(),
  preview: vi.fn(),
  toggle: vi.fn(),
  unlock: vi.fn(),
}))

vi.mock('@/api/moldingSample', () => ({ moldingSampleApi: moldingSampleApiMock }))
vi.mock('@/api/system', () => ({ systemApi: systemApiMock }))
vi.mock('@/composables/useNotificationSound', async () => {
  const { ref } = await import('vue')
  const soundEnabled = ref(true)
  const soundReady = ref(false)
  return {
    useNotificationSound: () => ({
      soundEnabled,
      soundReady,
      playNotificationSound: soundMock.play,
      previewSound: soundMock.preview,
      toggleSound: soundMock.toggle,
      unlockSound: soundMock.unlock,
    }),
  }
})

function createBusinessNotification(
  input: Partial<MoldingSampleNotificationResponse> & Pick<MoldingSampleNotificationResponse, 'id' | 'title'>,
): MoldingSampleNotificationResponse {
  return {
    order_id: `BP-${input.id}`,
    factory_id: 'huaxing',
    target_role: '工程部',
    target_department: 'engineering',
    target_module: 'engineering_molding_sample',
    event_type: '生产完成回传',
    message: `${input.title} 的业务消息`,
    from_status: '生产中',
    to_status: '已完成',
    status: '未读',
    actor_name: '系统',
    read_at: '',
    handled_at: '',
    created_at: '2026-07-18 08:00:00',
    ...input,
  }
}

function createSystemNotification(
  input: Partial<SystemNotificationResponse> & Pick<SystemNotificationResponse, 'id' | 'title'>,
): SystemNotificationResponse {
  return {
    target_user_id: '',
    target_permission: 'system:user_manage',
    target_factory_id: 'huaxing',
    target_department: 'engineering',
    type: 'user_registration',
    message: `${input.title} 的系统消息`,
    payload: { registration_request_id: `REQ-${input.id}` },
    status: 'unread',
    created_at: '2026-07-18 08:00:00',
    read_at: '',
    handled_at: '',
    ...input,
  }
}

function seedAccount(id = 'user-a', authorizationVersion = 1) {
  useAuthStore().applySession({
    id,
    username: id,
    display_name: id,
    roles: ['工程师'],
    permissions: ['molding_sample:notification_read'],
    grants: [{
      role_id: 'position_engineering_engineer',
      role_code: 'position_engineering_engineer',
      role_name: '工程师',
      factory_id: 'huaxing',
      department: 'engineering',
      permissions: ['molding_sample:notification_read'],
      scope_mode: 'local_operate',
      data_scope: 'department',
    }],
    factory_scopes: ['huaxing'],
    department_scopes: ['engineering'],
    authorization_version: authorizationVersion,
    authz_mode: 'legacy',
    force_password_change: false,
  })
}

type NotificationCenter = ReturnType<typeof useNotificationCenter>
const mountedWrappers: Array<ReturnType<typeof mount>> = []

function mountCenter() {
  let center: NotificationCenter | undefined
  const Harness = defineComponent({
    setup() {
      center = useNotificationCenter()
      return () => h('div')
    },
  })
  const wrapper = mount(Harness)
  mountedWrappers.push(wrapper)
  return {
    wrapper,
    center: () => center!,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('useNotificationCenter', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
    vi.clearAllMocks()
    moldingSampleApiMock.listNotifications.mockResolvedValue([])
    moldingSampleApiMock.updateNotification.mockResolvedValue({})
    systemApiMock.listNotifications.mockResolvedValue([])
    systemApiMock.updateNotification.mockResolvedValue({})
    soundMock.play.mockResolvedValue(true)
    soundMock.preview.mockResolvedValue(true)
    soundMock.toggle.mockResolvedValue(undefined)
    soundMock.unlock.mockResolvedValue(true)
    seedAccount()
  })

  afterEach(() => {
    mountedWrappers.splice(0).forEach((wrapper) => wrapper.unmount())
    vi.useRealTimers()
  })

  it('builds an initial baseline without toast or sound', async () => {
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createBusinessNotification({ id: 'HISTORY', title: '历史未读消息' }),
    ])

    const { center } = mountCenter()
    await flushPromises()

    expect(center().items.value.map((item) => item.title)).toEqual(['历史未读消息'])
    expect(center().currentToast.value).toBeNull()
    expect(soundMock.play).not.toHaveBeenCalled()
  })

  it('keeps AI operational alerts pending until the targeted recipient explicitly handles them', async () => {
    const alert = createSystemNotification({
      id: 'AI-ALERT-1',
      title: 'AI Provider 连续失败',
      type: 'ai_operational_alert',
      target_user_id: 'user-a',
      target_permission: '',
      target_factory_id: '',
      target_department: '',
      payload: {
        schema_version: 'ai-operational-alert-v1',
        alert_type: 'PROVIDER_FAILURE',
        observed_value: 5,
        threshold_value: 3,
        metadata_only: true,
      },
    })
    const registration = createSystemNotification({
      id: 'REGISTRATION-1',
      title: '普通系统通知',
    })
    systemApiMock.listNotifications.mockResolvedValue([alert, registration])

    const { center } = mountCenter()
    await flushPromises()

    const initialAlert = center().items.value.find((item) => item.id === alert.id)!
    expect(initialAlert.categoryLabel).toBe('AI 运维告警')
    expect(initialAlert.route).toBe('/workbench/ai')
    expect(initialAlert.isPending).toBe(true)

    await center().markNotificationRead(initialAlert)
    expect(center().items.value.find((item) => item.id === alert.id)?.status).toBe('read')
    expect(center().items.value.find((item) => item.id === alert.id)?.isPending).toBe(true)

    const handledAlert = {
      ...alert,
      status: 'handled',
      read_at: '2026-07-18 16:01:00',
      handled_at: '2026-07-18 16:02:00',
    }
    systemApiMock.updateNotification.mockResolvedValueOnce(handledAlert)
    await center().markNotificationHandled(center().items.value.find((item) => item.id === alert.id)!)

    expect(systemApiMock.updateNotification).toHaveBeenLastCalledWith(alert.id, { status: 'handled' })
    expect(center().items.value.find((item) => item.id === alert.id)?.status).toBe('handled')
    expect(center().items.value.find((item) => item.id === alert.id)?.isPending).toBe(false)

    systemApiMock.listNotifications.mockResolvedValue([{ ...alert, status: 'read' }, registration])
    await center().refreshNotifications('manual-refresh')
    expect(center().items.value.find((item) => item.id === alert.id)?.status).toBe('handled')

    const callCount = systemApiMock.updateNotification.mock.calls.length
    expect(center().markNotificationHandled(
      center().items.value.find((item) => item.id === registration.id)!,
    )).toBe(false)
    expect(systemApiMock.updateNotification).toHaveBeenCalledTimes(callCount)
  })

  it('restores a pending AI operational alert when acknowledgement fails', async () => {
    const alert = createSystemNotification({
      id: 'AI-ALERT-ACK-FAIL',
      title: 'AI Tool 连续失败',
      type: 'ai_operational_alert',
      target_user_id: 'user-a',
      target_permission: '',
      target_factory_id: '',
      target_department: '',
      status: 'read',
      read_at: '2026-07-18 16:01:00',
      payload: {
        schema_version: 'ai-operational-alert-v1',
        alert_type: 'TOOL_FAILURE',
        observed_value: 4,
        threshold_value: 3,
        metadata_only: true,
      },
    })
    systemApiMock.listNotifications.mockResolvedValue([alert])
    systemApiMock.updateNotification.mockRejectedValueOnce(new Error('network unavailable'))

    const { center } = mountCenter()
    await flushPromises()

    const acknowledged = await center().markNotificationHandled(center().items.value[0]!)

    expect(acknowledged).toBe(false)
    expect(center().items.value[0]?.status).toBe('read')
    expect(center().items.value[0]?.isPending).toBe(true)
    expect(center().sourceErrors.value).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: 'system' }),
    ]))
  })

  it('polls only a recent change window and merges changes into the full baseline', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-18T08:30:00Z'))
    const retained = createBusinessNotification({ id: 'RETAINED', title: '保留的历史消息' })
    const updated = createBusinessNotification({ id: 'UPDATED', title: '状态将更新' })
    moldingSampleApiMock.listNotifications.mockResolvedValueOnce([retained, updated])

    const { center } = mountCenter()
    await flushPromises()

    const arrival = createBusinessNotification({ id: 'ARRIVAL', title: '新增消息' })
    moldingSampleApiMock.listNotifications.mockResolvedValueOnce([
      { ...updated, status: '已处理', handled_at: '2026-07-18 16:29:30' },
      arrival,
    ])
    await center().refreshNotifications('background-poll')

    expect(moldingSampleApiMock.listNotifications).toHaveBeenLastCalledWith({
      changed_after: '2026-07-18T08:25:00.000Z',
    })
    expect(center().items.value.map((item) => item.id).sort()).toEqual([
      'ARRIVAL',
      'RETAINED',
      'UPDATED',
    ])
    expect(center().items.value.find((item) => item.id === 'UPDATED')?.status).toBe('handled')
  })

  it('interprets legacy and explicit-offset notification times in the business timezone', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-18T08:30:00Z'))

    expect(formatNotificationTime('2026-07-18 16:29:30')).toBe('刚刚')
    expect(formatNotificationTime('2026-07-18T08:00:00Z')).toBe('30 分钟前')
    expect(formatNotificationTime('2026-07-17T07:59:00Z')).toBe('2026-07-17 15:59')
    expect(formatNotificationTime('not-a-date')).toBe('not-a-date')
  })

  it('keeps an oversized same-timestamp baseline silent and announces the next boundary item once', async () => {
    const createdAt = '2026-07-18 08:00:00'
    const history = Array.from({ length: 250 }, (_, index) => createBusinessNotification({
      id: `HISTORY-${index}`,
      title: `历史消息 ${index}`,
      created_at: createdAt,
    }))
    moldingSampleApiMock.listNotifications.mockResolvedValue(history)

    const { center } = mountCenter()
    await flushPromises()
    await center().refreshNotifications('background-poll')

    expect(center().items.value).toHaveLength(250)
    expect(center().currentToast.value).toBeNull()
    expect(soundMock.play).not.toHaveBeenCalled()

    const boundaryItem = createBusinessNotification({
      id: 'HISTORY-250',
      title: '同秒新增消息',
      created_at: createdAt,
    })
    moldingSampleApiMock.listNotifications.mockResolvedValue([boundaryItem, ...history])

    await center().refreshNotifications('background-poll')

    expect(center().items.value).toHaveLength(251)
    expect(center().currentToast.value?.notification?.id).toBe('HISTORY-250')
    expect(soundMock.play).toHaveBeenCalledTimes(1)

    center().dismissCurrentToast()
    await center().refreshNotifications('background-poll')

    expect(center().currentToast.value).toBeNull()
    expect(soundMock.play).toHaveBeenCalledTimes(1)
  })

  it('announces new business and system notifications only on background refresh', async () => {
    const { center } = mountCenter()
    await flushPromises()

    const business = createBusinessNotification({ id: 'BUSINESS-NEW', title: '新增业务通知' })
    moldingSampleApiMock.listNotifications.mockResolvedValue([business])
    await center().refreshNotifications('manual-refresh')
    expect(center().items.value.map((item) => item.title)).toContain('新增业务通知')
    expect(center().currentToast.value).toBeNull()

    const system = createSystemNotification({ id: 'SYSTEM-NEW', title: '新增系统通知' })
    systemApiMock.listNotifications.mockResolvedValue([system])
    await center().refreshNotifications('background-poll')

    expect(center().currentToast.value?.title).toBe('新增系统通知')
    expect(soundMock.play).toHaveBeenCalledTimes(1)
  })

  it('queues three individual messages plus one overflow summary and sounds once', async () => {
    const { center } = mountCenter()
    await flushPromises()
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createBusinessNotification({ id: 'B1', title: '普通一', created_at: '2026-07-18 08:03:00' }),
      createBusinessNotification({ id: 'B2', title: '高优先二', event_type: '待主管审核', created_at: '2026-07-18 08:02:00' }),
      createBusinessNotification({ id: 'B3', title: '高优先三', event_type: '驳回异常', created_at: '2026-07-18 08:01:00' }),
      createBusinessNotification({ id: 'B4', title: '普通四', created_at: '2026-07-18 08:04:00' }),
    ])

    await center().refreshNotifications('background-poll')

    expect(center().currentToast.value?.title).toBe('高优先三')
    expect(center().queuedToastCount.value).toBe(3)
    expect(soundMock.play).toHaveBeenCalledTimes(1)

    center().dismissCurrentToast()
    center().dismissCurrentToast()
    center().dismissCurrentToast()
    expect(center().currentToast.value?.kind).toBe('summary')
    expect(center().currentToast.value?.title).toBe('另有 1 条新消息')
  })

  it('reconciles overflow summary counts as represented notifications become read', async () => {
    const { center } = mountCenter()
    await flushPromises()
    moldingSampleApiMock.listNotifications.mockResolvedValue(
      Array.from({ length: 5 }, (_, index) => createBusinessNotification({
        id: `OVERFLOW-${index + 1}`,
        title: `溢出消息 ${index + 1}`,
        created_at: `2026-07-18 08:0${index + 1}:00`,
      })),
    )

    await center().refreshNotifications('background-poll')

    expect(center().queuedToastCount.value).toBe(3)
    const firstOverflowItem = center().items.value.find((item) => item.id === 'OVERFLOW-4')
    expect(firstOverflowItem).toBeTruthy()
    await center().markNotificationRead(firstOverflowItem!)

    center().dismissCurrentToast()
    center().dismissCurrentToast()
    center().dismissCurrentToast()

    expect(center().currentToast.value?.kind).toBe('summary')
    expect(center().currentToast.value?.title).toBe('另有 1 条新消息')
    expect(center().currentToast.value?.notificationKeys).toEqual(['molding:OVERFLOW-5'])

    const remainingOverflowItem = center().items.value.find((item) => item.id === 'OVERFLOW-5')
    expect(remainingOverflowItem).toBeTruthy()
    await center().markNotificationRead(remainingOverflowItem!)

    expect(center().currentToast.value).toBeNull()
    expect(center().queuedToastCount.value).toBe(0)
    expect(moldingSampleApiMock.updateNotification).toHaveBeenCalledTimes(2)
  })

  it('removes a queued toast when that notification is read from the panel', async () => {
    const { center } = mountCenter()
    await flushPromises()
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createBusinessNotification({ id: 'QUEUE-1', title: '队列一', created_at: '2026-07-18 08:01:00' }),
      createBusinessNotification({ id: 'QUEUE-2', title: '队列二', created_at: '2026-07-18 08:02:00' }),
    ])
    await center().refreshNotifications('background-poll')

    const queuedItem = center().items.value.find((item) => item.key !== center().currentToast.value?.notification?.key)
    expect(queuedItem).toBeTruthy()
    expect(center().queuedToastCount.value).toBe(1)

    await center().markNotificationRead(queuedItem!)

    expect(center().queuedToastCount.value).toBe(0)
    expect(center().currentToast.value?.notification?.key).not.toBe(queuedItem?.key)
  })

  it('does not downgrade a stale handled toast to read after refresh reconciliation', async () => {
    const { center } = mountCenter()
    await flushPromises()
    const unread = createBusinessNotification({ id: 'STALE-HANDLED', title: '稍后已完成的任务' })
    moldingSampleApiMock.listNotifications.mockResolvedValue([unread])
    await center().refreshNotifications('background-poll')
    const staleToast = center().currentToast.value
    expect(staleToast?.notification).toBeTruthy()

    moldingSampleApiMock.listNotifications.mockResolvedValue([{ ...unread, status: '已处理' }])
    await center().refreshNotifications('background-poll')
    expect(center().currentToast.value).toBeNull()
    moldingSampleApiMock.updateNotification.mockClear()

    center().activateToast(staleToast!)
    await flushPromises()

    expect(moldingSampleApiMock.updateNotification).not.toHaveBeenCalled()
  })

  it('does not reannounce the same notification on a later poll', async () => {
    const { center } = mountCenter()
    await flushPromises()
    const notification = createBusinessNotification({ id: 'ONCE', title: '只提醒一次' })
    moldingSampleApiMock.listNotifications.mockResolvedValue([notification])

    await center().refreshNotifications('background-poll')
    center().dismissCurrentToast()
    await center().refreshNotifications('background-poll')

    expect(center().currentToast.value).toBeNull()
    expect(soundMock.play).toHaveBeenCalledTimes(1)
  })

  it('refreshes from the panel without producing a duplicate toast', async () => {
    const { center } = mountCenter()
    await flushPromises()
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createBusinessNotification({ id: 'PANEL', title: '面板刷新消息' }),
    ])

    center().togglePanel()
    await flushPromises()

    expect(center().isPanelOpen.value).toBe(true)
    expect(center().items.value.map((item) => item.title)).toContain('面板刷新消息')
    expect(center().currentToast.value).toBeNull()
    expect(soundMock.play).not.toHaveBeenCalled()
  })

  it('treats visibility-resume and authorization changes as silent baseline refreshes', async () => {
    const { center } = mountCenter()
    await flushPromises()
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createBusinessNotification({ id: 'RESUME', title: '恢复可见消息' }),
    ])

    await center().refreshNotifications('visibility-resume')
    expect(center().items.value.map((item) => item.title)).toContain('恢复可见消息')
    expect(center().currentToast.value).toBeNull()

    seedAccount('user-a', 2)
    await flushPromises()
    expect(center().currentToast.value).toBeNull()
    expect(soundMock.play).not.toHaveBeenCalled()
  })

  it('keeps the successful source and stale data when either API fails', async () => {
    const oldBusiness = createBusinessNotification({ id: 'OLD-B', title: '保留业务旧数据' })
    const oldSystem = createSystemNotification({ id: 'OLD-S', title: '保留系统旧数据' })
    moldingSampleApiMock.listNotifications.mockResolvedValue([oldBusiness])
    systemApiMock.listNotifications.mockResolvedValue([oldSystem])
    const { center } = mountCenter()
    await flushPromises()

    const newSystem = createSystemNotification({ id: 'NEW-S', title: '系统新数据' })
    moldingSampleApiMock.listNotifications.mockRejectedValue(new Error('business offline'))
    systemApiMock.listNotifications.mockResolvedValue([newSystem])
    await center().refreshNotifications('manual-refresh')

    expect(center().items.value.map((item) => item.title)).toEqual(expect.arrayContaining(['保留业务旧数据', '系统新数据']))
    expect(center().sourceErrors.value.map((error) => error.source)).toContain('molding')

    const newBusiness = createBusinessNotification({ id: 'NEW-B', title: '业务新数据' })
    moldingSampleApiMock.listNotifications.mockResolvedValue([newBusiness])
    systemApiMock.listNotifications.mockRejectedValue(new Error('system offline'))
    await center().refreshNotifications('manual-refresh')

    expect(center().items.value.map((item) => item.title)).toEqual(expect.arrayContaining(['业务新数据', '系统新数据']))
    expect(center().sourceErrors.value.map((error) => error.source)).toContain('system')
  })

  it('discards a slower response from the previous account', async () => {
    const oldRequest = deferred<MoldingSampleNotificationResponse[]>()
    moldingSampleApiMock.listNotifications
      .mockImplementationOnce(() => oldRequest.promise)
      .mockResolvedValue([createBusinessNotification({ id: 'ACCOUNT-B', title: '账号 B 消息' })])

    const { center } = mountCenter()
    await flushPromises()
    seedAccount('user-b', 2)
    await flushPromises()
    oldRequest.resolve([createBusinessNotification({ id: 'ACCOUNT-A', title: '账号 A 迟到消息' })])
    await flushPromises()

    expect(center().items.value.map((item) => item.title)).toContain('账号 B 消息')
    expect(center().items.value.map((item) => item.title)).not.toContain('账号 A 迟到消息')
    expect(center().currentToast.value).toBeNull()
  })

  it('does not reuse an in-flight read mutation across accounts with the same notification id', async () => {
    const firstMutation = deferred<Record<string, never>>()
    const accountANotification = createBusinessNotification({ id: 'SHARED-ID', title: '账号 A 同号消息' })
    moldingSampleApiMock.listNotifications.mockResolvedValue([accountANotification])
    moldingSampleApiMock.updateNotification
      .mockImplementationOnce(() => firstMutation.promise)
      .mockResolvedValue({})
    const { center } = mountCenter()
    await flushPromises()

    const firstRead = center().markNotificationRead(center().items.value[0]!)
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createBusinessNotification({ id: 'SHARED-ID', title: '账号 B 同号消息' }),
    ])
    seedAccount('user-b', 2)
    await flushPromises()

    await center().markNotificationRead(center().items.value[0]!)
    expect(moldingSampleApiMock.updateNotification).toHaveBeenCalledTimes(2)
    expect(center().items.value[0]?.status).toBe('read')

    firstMutation.resolve({})
    await firstRead
    expect(center().items.value[0]?.title).toBe('账号 B 同号消息')
    expect(center().items.value[0]?.status).toBe('read')
  })

  it('uses a safe internal-quote route from the backend-filtered system feed', async () => {
    useAppStore().setActiveFactory('huakang-a')
    systemApiMock.listNotifications.mockResolvedValue([
      createSystemNotification({
        id: 'QUOTE-1',
        title: '内部报价待协作',
        type: 'internal_quote',
        target_factory_id: 'huakang-c',
        target_permission: 'internal_quote:read',
        payload: {
          quote_no: 'IQ-001',
          route: '/modules/sales-business/internal-quote-desk/quote-1?section=engineering&factory=huaxing',
        },
      }),
      createSystemNotification({
        id: 'QUOTE-2',
        title: '内部报价待汇总',
        type: 'internal_quote',
        target_factory_id: 'huakang-d',
        target_permission: 'internal_quote:read',
        payload: {
          quote_no: 'IQ-002',
          route: '/modules/sales-business/internal-quote-desk/quote-2/summary',
        },
      }),
      createSystemNotification({
        id: 'QUOTE-UNSAFE',
        title: '内部报价异常地址',
        type: 'internal_quote',
        target_factory_id: 'group',
        target_permission: 'internal_quote:read',
        payload: {
          quote_no: 'IQ-003',
          route: '/modules/sales-business/internal-quote-desk/quote-3?redirect=https://example.com',
        },
      }),
    ])

    const { center } = mountCenter()
    await flushPromises()

    const quoteItem = center().items.value.find((item) => item.id === 'QUOTE-1')
    const summaryItem = center().items.value.find((item) => item.id === 'QUOTE-2')
    const unsafeItem = center().items.value.find((item) => item.id === 'QUOTE-UNSAFE')
    expect(quoteItem?.route).toBe('/modules/sales-business/internal-quote-desk/quote-1/collaboration?section=engineering&factory=huakang-c')
    expect(summaryItem?.route).toBe('/modules/sales-business/internal-quote-desk/quote-2/summary?factory=huakang-d')
    expect(unsafeItem?.route).toBe('/modules/sales-business/internal-quote-desk')
    expect(quoteItem?.contextLabel).toContain('engineering')
  })

  it('forces customer-price artifact notifications onto the conversion workflow route', async () => {
    useAppStore().setActiveFactory('huakang-a')
    systemApiMock.listNotifications.mockResolvedValue([
      createSystemNotification({
        id: 'QUOTE-ARTIFACT',
        title: '内部报价 artifact 可导入',
        type: 'internal_quote',
        target_factory_id: 'huakang-d',
        target_permission: 'customer_price:import_internal_quote',
        payload: {
          event: 'customer_price_artifact_available',
          quote_no: 'IQ-ARTIFACT',
          route: '/modules/sales-business/internal-quote-desk/quote-artifact/export',
        },
      }),
    ])

    const { center } = mountCenter()
    await flushPromises()

    expect(center().items.value[0]?.route).toBe('/modules/sales-business/customer-price-conversion?factory=huakang-d')
  })

  it('counts only actionable internal-quote events as pending work', async () => {
    systemApiMock.listNotifications.mockResolvedValue([
      createSystemNotification({
        id: 'QUOTE-ACTION',
        title: '内部报价待审核',
        type: 'internal_quote',
        status: 'read',
        payload: {
          event: 'section_submitted',
          quote_no: 'IQ-ACTION',
          route: '/modules/sales-business/internal-quote-desk/quote-action',
        },
      }),
      createSystemNotification({
        id: 'QUOTE-RESULT',
        title: '内部报价已放行',
        type: 'internal_quote',
        status: 'read',
        payload: {
          event: 'final_release_approved',
          quote_no: 'IQ-RESULT',
          route: '/modules/sales-business/internal-quote-desk/quote-result',
        },
      }),
      createSystemNotification({
        id: 'QUOTE-HANDLED',
        title: '内部报价审核已完成',
        type: 'internal_quote',
        status: 'handled',
        payload: {
          event: 'section_submitted',
          quote_no: 'IQ-HANDLED',
          route: '/modules/sales-business/internal-quote-desk/quote-handled',
        },
      }),
    ])

    const { center } = mountCenter()
    await flushPromises()

    expect(center().items.value).toHaveLength(3)
    expect(center().pendingCount.value).toBe(1)
    expect(center().items.value.find((item) => item.id === 'QUOTE-ACTION')?.isPending).toBe(true)
    expect(center().items.value.find((item) => item.id === 'QUOTE-RESULT')?.isPending).toBe(false)
    expect(center().items.value.find((item) => item.id === 'QUOTE-HANDLED')?.isPending).toBe(false)
  })

  it('does not reset a live queue on an ordinary same-account session refresh', async () => {
    const { center } = mountCenter()
    await flushPromises()
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createBusinessNotification({ id: 'KEEP-QUEUE', title: '保留队列消息' }),
    ])
    await center().refreshNotifications('background-poll')
    expect(center().currentToast.value?.title).toBe('保留队列消息')

    seedAccount('user-a', 1)
    await flushPromises()

    expect(center().currentToast.value?.title).toBe('保留队列消息')
    expect(soundMock.play).toHaveBeenCalledTimes(1)
  })

  it('keeps panel-visible arrivals inside the panel instead of covering it', async () => {
    const { center } = mountCenter()
    await flushPromises()
    center().togglePanel()
    await flushPromises()
    moldingSampleApiMock.listNotifications.mockResolvedValue([
      createBusinessNotification({ id: 'IN-PANEL', title: '面板内新增' }),
    ])

    await center().refreshNotifications('background-poll')

    expect(center().currentToast.value).toBeNull()
    expect(center().newWhilePanelOpenCount.value).toBe(1)
    expect(soundMock.play).not.toHaveBeenCalled()
  })

  it('stops polling offline, refreshes online, and does not restart after unmount', async () => {
    vi.useFakeTimers()
    const onlineDescriptor = Object.getOwnPropertyDescriptor(navigator, 'onLine')
    let online = true
    Object.defineProperty(navigator, 'onLine', { configurable: true, get: () => online })
    try {
      const { wrapper } = mountCenter()
      await flushPromises()
      expect(moldingSampleApiMock.listNotifications).toHaveBeenCalledTimes(1)

      online = false
      window.dispatchEvent(new Event('offline'))
      await vi.advanceTimersByTimeAsync(50_000)
      expect(moldingSampleApiMock.listNotifications).toHaveBeenCalledTimes(1)

      online = true
      window.dispatchEvent(new Event('online'))
      await flushPromises()
      expect(moldingSampleApiMock.listNotifications).toHaveBeenCalledTimes(2)

      wrapper.unmount()
      await vi.advanceTimersByTimeAsync(120_000)
      expect(moldingSampleApiMock.listNotifications).toHaveBeenCalledTimes(2)
    } finally {
      if (onlineDescriptor) Object.defineProperty(navigator, 'onLine', onlineDescriptor)
      else Reflect.deleteProperty(navigator, 'onLine')
    }
  })

  it('does not refresh a hidden page on online until visibility resumes', async () => {
    const visibilityDescriptor = Object.getOwnPropertyDescriptor(document, 'visibilityState')
    let visibilityState: DocumentVisibilityState = 'visible'
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibilityState })
    try {
      mountCenter()
      await flushPromises()
      expect(moldingSampleApiMock.listNotifications).toHaveBeenCalledTimes(1)

      visibilityState = 'hidden'
      document.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event('online'))
      await flushPromises()
      expect(moldingSampleApiMock.listNotifications).toHaveBeenCalledTimes(1)

      visibilityState = 'visible'
      document.dispatchEvent(new Event('visibilitychange'))
      await flushPromises()
      expect(moldingSampleApiMock.listNotifications).toHaveBeenCalledTimes(2)
      expect(soundMock.play).not.toHaveBeenCalled()
    } finally {
      if (visibilityDescriptor) Object.defineProperty(document, 'visibilityState', visibilityDescriptor)
      else Reflect.deleteProperty(document, 'visibilityState')
    }
  })

  it('serializes cross-tab claims so only one tab announces and sounds', async () => {
    const originalLocks = (navigator as Navigator & { locks?: unknown }).locks
    let lockTail = Promise.resolve()
    const requestedLocks: string[] = []
    Object.defineProperty(navigator, 'locks', {
      configurable: true,
      value: {
        request: <T>(_name: string, callback: () => T | Promise<T>) => {
          requestedLocks.push(_name)
          const result = lockTail.then(callback)
          lockTail = result.then(() => undefined, () => undefined)
          return result
        },
      },
    })
    try {
      const first = mountCenter()
      const second = mountCenter()
      await flushPromises()
      moldingSampleApiMock.listNotifications.mockResolvedValue([
        createBusinessNotification({ id: 'CROSS-TAB', title: '跨标签消息' }),
      ])

      await Promise.all([
        first.center().refreshNotifications('background-poll'),
        second.center().refreshNotifications('background-poll'),
      ])

      const visibleToastCount = [first.center(), second.center()].filter((center) => center.currentToast.value).length
      expect(visibleToastCount).toBe(1)
      expect(soundMock.play).toHaveBeenCalledTimes(1)
      expect(requestedLocks).toEqual(['rr.notification.claim.user-a', 'rr.notification.claim.user-a'])
    } finally {
      if (originalLocks === undefined) Reflect.deleteProperty(navigator, 'locks')
      else Object.defineProperty(navigator, 'locks', { configurable: true, value: originalLocks })
    }
  })
})

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { moldingSampleApi, type MoldingSampleNotificationResponse } from '@/api/moldingSample'
import { systemApi, type SystemNotificationResponse } from '@/api/system'
import { formatBusinessDateTime, parseBusinessTimestamp } from '@/lib/dateTime'
import { getApiErrorMessage } from '@/lib/http'
import { getFactoryScopedRoute, isProductionFactoryContextId } from '@/data/enterpriseMock'
import { useAuthStore } from '@/stores/auth'
import { useNotificationSound } from '@/composables/useNotificationSound'

export type NotificationCenterSource = 'molding' | 'system'
export type NotificationCenterStatus = 'unread' | 'read' | 'handled'
export type NotificationSeverity = 'high' | 'normal'
export type NotificationLoadReason = 'initial' | 'account-change' | 'background-poll' | 'panel-open' | 'manual-refresh' | 'visibility-resume'

export interface NotificationCenterItem {
  key: string
  id: string
  source: NotificationCenterSource
  category: string
  severity: NotificationSeverity
  status: NotificationCenterStatus
  isUnread: boolean
  isPending: boolean
  factoryId: string
  department: string
  role: string
  title: string
  summary: string
  contextLabel: string
  route: string
  actionLabel: string
  createdAt: string
  categoryLabel: string
  referenceLabel: string
  targetLabel: string
  raw: MoldingSampleNotificationResponse | SystemNotificationResponse
}

export interface NotificationToastEntry {
  key: string
  kind: 'notification' | 'summary'
  notification?: NotificationCenterItem
  title: string
  summary: string
  categoryLabel: string
  contextLabel: string
  createdAt: string
  route: string
  notificationKeys?: string[]
}

type SourceLoadState = 'idle' | 'loading' | 'ready' | 'error'

interface SourceStatus {
  state: SourceLoadState
  error: string
}

interface SharedAnnouncement {
  key: string
  announcedAt: number
}

interface SharedObservationCursor {
  timestamp: number
  boundaryKeys: string[]
  saturated: boolean
}

type SharedObservationWatermarks = Partial<Record<NotificationCenterSource, SharedObservationCursor>>

const NOTIFICATION_REFRESH_INTERVAL_MS = 25_000
const MAX_NOTIFICATION_REFRESH_INTERVAL_MS = 120_000
const NOTIFICATION_CHANGE_LOOKBACK_MS = 5 * 60 * 1_000
const NOTIFICATION_TOAST_TIMEOUT_MS = 9_000
const SHARED_ANNOUNCEMENT_TTL_MS = 6 * 60 * 60 * 1_000
const MAX_SHARED_ANNOUNCEMENTS = 200
const MAX_WATERMARK_BOUNDARY_KEYS = 500
const INTERNAL_QUOTE_ROUTE_BASE = '/modules/sales-business/internal-quote-desk'
const INTERNAL_QUOTE_ROUTE_PATTERN = /^\/modules\/sales-business\/internal-quote-desk\/([A-Za-z0-9][A-Za-z0-9._~-]{0,63})(?:\/(collaboration|summary|export))?$/
const UNSAFE_INTERNAL_QUOTE_QUERY_KEYS = new Set([
  'continue',
  'next',
  'redirect',
  'redirect_uri',
  'return_to',
  'returnurl',
  'url',
])
const ACTIONABLE_INTERNAL_QUOTE_EVENTS = new Set([
  'quote_created',
  'quote_cloned',
  'section_rejected',
  'section_reopened',
  'reference_snapshot_updated',
  'section_submitted',
  'section_na_requested',
  'ready_for_final_review',
  'final_release_rejected',
  'final_release_invalidated',
  'final_release_submitted',
  'customer_price_artifact_available',
])

function normalizeMoldingStatus(status: MoldingSampleNotificationResponse['status']): NotificationCenterStatus {
  if (status === '已处理') return 'handled'
  if (status === '已读') return 'read'
  return 'unread'
}

function normalizeSystemStatus(status: string): NotificationCenterStatus {
  if (status === 'handled') return 'handled'
  if (status === 'read') return 'read'
  return 'unread'
}

function notificationTimestamp(value: string) {
  return parseBusinessTimestamp(value) ?? 0
}

export function formatNotificationTime(value: string) {
  const timestamp = notificationTimestamp(value)
  if (!timestamp) return value
  const elapsed = Date.now() - timestamp
  if (elapsed >= 0 && elapsed < 60_000) return '刚刚'
  if (elapsed >= 60_000 && elapsed < 60 * 60_000) return `${Math.floor(elapsed / 60_000)} 分钟前`
  if (elapsed >= 60 * 60_000 && elapsed < 24 * 60 * 60_000) return `${Math.floor(elapsed / (60 * 60_000))} 小时前`
  return formatBusinessDateTime(value, { fallback: value })
}

export function useNotificationCenter() {
  const authStore = useAuthStore()
  const {
    soundEnabled,
    soundReady,
    playNotificationSound,
    previewSound,
    toggleSound,
    unlockSound,
  } = useNotificationSound()

  const isPanelOpen = ref(false)
  const bellButtonRef = ref<HTMLButtonElement | null>(null)
  const popoverRef = ref<HTMLElement | null>(null)
  const panelRef = ref<HTMLElement | null>(null)
  const moldingNotifications = ref<MoldingSampleNotificationResponse[]>([])
  const systemNotifications = ref<SystemNotificationResponse[]>([])
  const sourceStatus = ref<Record<NotificationCenterSource, SourceStatus>>({
    molding: { state: 'idle', error: '' },
    system: { state: 'idle', error: '' },
  })
  const toastQueue = ref<NotificationToastEntry[]>([])
  const newWhilePanelOpenCount = ref(0)
  const seenNotificationKeys = new Set<string>()
  const initializedSources = new Set<NotificationCenterSource>()
  const readOverrides = new Set<string>()
  let loadSequence = 0
  let disposed = false
  let refreshTimer: ReturnType<typeof window.setTimeout> | undefined
  let toastTimer: ReturnType<typeof window.setTimeout> | undefined
  let toastExpiresAt = 0
  let toastRemainingMs = NOTIFICATION_TOAST_TIMEOUT_MS
  let currentPollInterval = NOTIFICATION_REFRESH_INTERVAL_MS
  let activeLoadPromise: Promise<boolean> | undefined
  let activeLoadAccountKey = ''
  let hasInitializedAccountContext = false
  const readMutationPromises = new Map<string, Promise<boolean>>()

  const accountNotificationKey = computed(() => [
    authStore.currentUser?.id ?? '',
    authStore.authorizationVersion,
    authStore.authzMode,
  ].join('|'))

  const sharedAnnouncementStorageKey = computed(() => (
    `rr.notification.announced.${authStore.currentUser?.id || 'anonymous'}`
  ))

  const sharedWatermarkStorageKey = computed(() => (
    `rr.notification.watermarks.${authStore.currentUser?.id || 'anonymous'}`
  ))

  function hasMoldingPermission() {
    return authStore.isAuthenticated && authStore.can('molding_sample:notification_read')
  }

  function hasSystemPermission() {
    // The backend applies target_user, permission, factory, and department scope.
    // All authenticated users may therefore ask for their already-filtered system feed.
    return authStore.isAuthenticated
  }

  function isAdminAccount() {
    return authStore.roles.includes('系统管理员') || authStore.can('system:user_manage')
  }

  function getNotificationDepartments(notification: MoldingSampleNotificationResponse) {
    if (notification.target_module === 'production_molding_sample_task') return ['production', 'molding']
    if (notification.target_department) {
      if (['production', 'molding'].includes(notification.target_department)) return ['production', 'molding']
      if (['pmc-warehouse', 'warehouse'].includes(notification.target_department)) return ['pmc-warehouse', 'warehouse']
      return [notification.target_department]
    }
    if (/经理|管理/.test(notification.target_role)) return ['management']
    if (/啤机|生产/.test(notification.target_role)) return ['production', 'molding']
    if (/仓|PMC/.test(notification.target_role)) return ['pmc-warehouse', 'warehouse']
    return ['engineering']
  }

  function isNotificationFactoryInScope(notification: MoldingSampleNotificationResponse) {
    return getNotificationDepartments(notification).some((department) =>
      authStore.can('molding_sample:notification_read', notification.factory_id, department),
    )
  }

  function getAccountTargetRoles() {
    const targets = new Set(authStore.roles)
    const roleNames = authStore.roles
    if (roleNames.some((role) => role === '工程部' || role.includes('工程师')) || authStore.can('molding_sample:create')) {
      targets.add('工程部')
    }
    if (roleNames.some((role) => role.includes('工程主管')) || authStore.can('molding_sample:supervisor_review')) {
      targets.add('工程主管')
    }
    if (roleNames.some((role) => role.includes('经理')) || authStore.can('molding_sample:manager_review')) {
      targets.add('经理')
    }
    if (roleNames.some((role) => role.includes('啤机')) || authStore.can('molding_sample:production_read')) {
      targets.add('啤机部')
    }
    if (roleNames.some((role) => /仓|PMC/.test(role)) || authStore.can('molding_sample:warehouse_requisition') || authStore.can('molding_sample:inventory_issue')) {
      targets.add('仓库')
    }
    return targets
  }

  function isNotificationRoleForCurrentAccount(notification: MoldingSampleNotificationResponse) {
    return isAdminAccount() || getAccountTargetRoles().has(notification.target_role)
  }

  const scopedMoldingNotifications = computed(() => moldingNotifications.value.filter((notification) =>
    isNotificationFactoryInScope(notification)
    && isNotificationRoleForCurrentAccount(notification),
  ))

  const scopedSystemNotifications = computed(() => systemNotifications.value)

  function getMoldingRoute(notification: MoldingSampleNotificationResponse) {
    const params = new URLSearchParams({
      factory: notification.factory_id,
      order_id: notification.order_id,
    })
    return notification.target_module === 'production_molding_sample_task'
      ? `/modules/production/molding-sample-tasks?${params.toString()}`
      : `/modules/molding-sample?${params.toString()}`
  }

  function getSystemRoute(notification: SystemNotificationResponse) {
    if (notification.type === 'internal_quote') {
      let targetRoute = INTERNAL_QUOTE_ROUTE_BASE
      if (notification.payload.event === 'customer_price_artifact_available') {
        targetRoute = '/modules/sales-business/customer-price-conversion'
      } else {
        const payloadRoute = typeof notification.payload.route === 'string' ? notification.payload.route.trim() : ''
        const [payloadPath, rawQuery = ''] = payloadRoute.split('?', 2)
        const routeMatch = payloadPath?.match(INTERNAL_QUOTE_ROUTE_PATTERN)
        const query = new URLSearchParams(rawQuery)
        const hasUnsafeQuery = [...query.keys()].some((key) =>
          UNSAFE_INTERNAL_QUOTE_QUERY_KEYS.has(key.toLowerCase()),
        )
        if (routeMatch && !hasUnsafeQuery) {
          const [, quoteId, destination = 'collaboration'] = routeMatch
          const normalizedQuery = query.toString()
          targetRoute = `${INTERNAL_QUOTE_ROUTE_BASE}/${quoteId}/${destination}${normalizedQuery ? `?${normalizedQuery}` : ''}`
        }
      }

      return isProductionFactoryContextId(notification.target_factory_id)
        ? getFactoryScopedRoute(targetRoute, notification.target_factory_id)
        : targetRoute
    }
    if (notification.type === 'password_reset') {
      const resetRequestId = typeof notification.payload.password_reset_request_id === 'string'
        ? notification.payload.password_reset_request_id
        : ''
      return resetRequestId
        ? `/system/users?tab=password-reset&request_id=${encodeURIComponent(resetRequestId)}`
        : '/system/users?tab=password-reset'
    }
    const requestId = typeof notification.payload.registration_request_id === 'string'
      ? notification.payload.registration_request_id
      : ''
    return requestId ? `/system/users?request_id=${encodeURIComponent(requestId)}` : '/system/users'
  }

  function moldingSeverity(notification: MoldingSampleNotificationResponse): NotificationSeverity {
    return /审核|驳回|问题|异常|待主管|待经理/.test(`${notification.event_type}${notification.title}`)
      ? 'high'
      : 'normal'
  }

  function normalizeMoldingNotification(notification: MoldingSampleNotificationResponse): NotificationCenterItem {
    return {
      key: `molding:${notification.id}`,
      id: notification.id,
      source: 'molding',
      category: notification.target_module,
      severity: moldingSeverity(notification),
      status: normalizeMoldingStatus(notification.status),
      isUnread: notification.status === '未读',
      isPending: notification.status !== '已处理',
      factoryId: notification.factory_id,
      department: getNotificationDepartments(notification)[0] ?? '',
      role: notification.target_role,
      title: notification.title,
      summary: notification.message,
      contextLabel: [notification.order_id, notification.factory_id, notification.target_role].filter(Boolean).join(' · '),
      route: getMoldingRoute(notification),
      actionLabel: '查看详情',
      createdAt: notification.created_at,
      categoryLabel: notification.target_module === 'production_molding_sample_task' ? '生产任务' : '啤办流程',
      referenceLabel: notification.order_id,
      targetLabel: notification.target_role,
      raw: notification,
    }
  }

  function normalizeSystemNotification(notification: SystemNotificationResponse): NotificationCenterItem {
    const internalQuoteEvent = typeof notification.payload.event === 'string' ? notification.payload.event : ''
    const isPending = notification.status !== 'handled'
      && (notification.type !== 'internal_quote' || ACTIONABLE_INTERNAL_QUOTE_EVENTS.has(internalQuoteEvent))
    return {
      key: `system:${notification.id}`,
      id: notification.id,
      source: 'system',
      category: notification.type,
      severity: ['password_reset', 'user_registration'].includes(notification.type) ? 'high' : 'normal',
      status: normalizeSystemStatus(notification.status),
      isUnread: notification.status === 'unread',
      isPending,
      factoryId: notification.target_factory_id,
      department: notification.target_department ?? '',
      role: notification.target_permission,
      title: notification.title,
      summary: notification.message,
      contextLabel: [
        notification.target_factory_id,
        notification.target_department,
        notification.type === 'password_reset'
          ? '账号服务'
          : notification.type === 'internal_quote' ? '内部报价' : '用户与授权',
      ].filter(Boolean).join(' · '),
      route: getSystemRoute(notification),
      actionLabel: '查看详情',
      createdAt: notification.created_at,
      categoryLabel: notification.type === 'password_reset'
        ? '密码重置'
        : notification.type === 'internal_quote' ? '内部报价' : '系统通知',
      referenceLabel: notification.type === 'password_reset'
        ? '账号服务'
        : notification.type === 'internal_quote' ? String(notification.payload.quote_no || '内部报价') : '用户与授权',
      targetLabel: notification.type === 'internal_quote' ? '业务协作' : '系统管理',
      raw: notification,
    }
  }

  const items = computed(() => [
    ...scopedMoldingNotifications.value.map(normalizeMoldingNotification),
    ...scopedSystemNotifications.value.map(normalizeSystemNotification),
  ].sort((left, right) => notificationTimestamp(right.createdAt) - notificationTimestamp(left.createdAt)))

  const unreadCount = computed(() => items.value.filter((item) => item.status === 'unread').length)
  const pendingCount = computed(() => items.value.filter((item) => item.isPending).length)
  const currentToast = computed(() => toastQueue.value[0] ?? null)
  const queuedToastCount = computed(() => Math.max(0, toastQueue.value.length - 1))
  const isRefreshing = computed(() => Object.values(sourceStatus.value).some((source) => source.state === 'loading'))
  const sourceErrors = computed(() => Object.entries(sourceStatus.value)
    .filter(([, status]) => status.error)
    .map(([source, status]) => ({
      source: source as NotificationCenterSource,
      label: source === 'molding' ? '业务通知' : '系统通知',
      message: status.error,
    })))
  const state = computed<SourceLoadState>(() => {
    const activeSources = [
      ...(hasMoldingPermission() ? [sourceStatus.value.molding] : []),
      ...(hasSystemPermission() ? [sourceStatus.value.system] : []),
    ]
    if (!activeSources.length) return 'idle'
    if (!items.value.length && activeSources.some((source) => source.state === 'loading')) return 'loading'
    if (!items.value.length && activeSources.every((source) => source.state === 'error')) return 'error'
    return 'ready'
  })

  function updateSourceStatus(source: NotificationCenterSource, status: SourceStatus) {
    sourceStatus.value = { ...sourceStatus.value, [source]: status }
  }

  function rememberKey(target: Set<string>, key: string) {
    if (target.has(key)) target.delete(key)
    target.add(key)
    while (target.size > MAX_SHARED_ANNOUNCEMENTS) {
      const oldestKey = target.values().next().value
      if (typeof oldestKey !== 'string') break
      target.delete(oldestKey)
    }
  }

  function readOverrideKey(itemKey: string, accountKey = accountNotificationKey.value) {
    return `${accountKey}:${itemKey}`
  }

  function applyReadOverridesToMolding(source: MoldingSampleNotificationResponse[]) {
    return source.map((notification) => (
      notification.status === '未读' && readOverrides.has(readOverrideKey(`molding:${notification.id}`))
        ? { ...notification, status: '已读' as const, read_at: notification.read_at || new Date().toISOString() }
        : notification
    ))
  }

  function applyReadOverridesToSystem(source: SystemNotificationResponse[]) {
    return source.map((notification) => {
      const overrideKey = readOverrideKey(`system:${notification.id}`)
      return notification.status === 'unread' && readOverrides.has(overrideKey)
        ? { ...notification, status: 'read' as const, read_at: notification.read_at || new Date().toISOString() }
        : notification
    })
  }

  function mergeNotificationsById<T extends { id: string }>(current: T[], changes: T[]) {
    const merged = new Map(current.map((notification) => [notification.id, notification]))
    changes.forEach((notification) => merged.set(notification.id, notification))
    return [...merged.values()]
  }

  function readSharedAnnouncements(storageKey = sharedAnnouncementStorageKey.value) {
    if (typeof window === 'undefined') return [] as SharedAnnouncement[]
    try {
      const rawValue = window.localStorage.getItem(storageKey)
      const parsed = rawValue ? JSON.parse(rawValue) : []
      if (!Array.isArray(parsed)) return []
      const cutoff = Date.now() - SHARED_ANNOUNCEMENT_TTL_MS
      return parsed.filter((item): item is SharedAnnouncement => (
        typeof item?.key === 'string'
        && typeof item?.announcedAt === 'number'
        && item.announcedAt >= cutoff
      ))
    } catch {
      return []
    }
  }

  function persistSharedAnnouncements(records: SharedAnnouncement[], storageKey = sharedAnnouncementStorageKey.value) {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(
        storageKey,
        JSON.stringify(records.slice(-MAX_SHARED_ANNOUNCEMENTS)),
      )
    } catch {
      // A full or disabled storage area must not break notification refreshes.
    }
  }

  function readSharedWatermarks(storageKey = sharedWatermarkStorageKey.value): SharedObservationWatermarks {
    if (typeof window === 'undefined') return {}
    try {
      const rawValue = window.localStorage.getItem(storageKey)
      const parsed = rawValue ? JSON.parse(rawValue) : {}
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
      const watermarks: SharedObservationWatermarks = {}
      ;(['molding', 'system'] as NotificationCenterSource[]).forEach((source) => {
        const rawCursor = parsed[source]
        if (typeof rawCursor === 'number' && Number.isFinite(rawCursor) && rawCursor >= 0) {
          watermarks[source] = { timestamp: rawCursor, boundaryKeys: [], saturated: true }
          return
        }
        if (!rawCursor || typeof rawCursor !== 'object' || Array.isArray(rawCursor)) return
        const timestamp = Number(rawCursor.timestamp)
        if (!Number.isFinite(timestamp) || timestamp < 0) return
        const boundaryCandidates: unknown[] = Array.isArray(rawCursor.boundaryKeys)
          ? rawCursor.boundaryKeys
          : []
        const rawBoundaryKeys = boundaryCandidates.filter(
          (key): key is string => typeof key === 'string',
        )
        const saturated = rawCursor.saturated === true || rawBoundaryKeys.length > MAX_WATERMARK_BOUNDARY_KEYS
        watermarks[source] = {
          timestamp,
          boundaryKeys: saturated ? [] : [...new Set(rawBoundaryKeys)],
          saturated,
        }
      })
      return watermarks
    } catch {
      return {}
    }
  }

  function persistSharedWatermarks(
    watermarks: SharedObservationWatermarks,
    storageKey = sharedWatermarkStorageKey.value,
  ) {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(watermarks))
    } catch {
      // A full or disabled storage area must not break notification refreshes.
    }
  }

  function rememberItemsInChronologicalOrder(sourceItems: NotificationCenterItem[]) {
    [...sourceItems]
      .sort((left, right) => notificationTimestamp(left.createdAt) - notificationTimestamp(right.createdAt))
      .forEach((item) => rememberKey(seenNotificationKeys, item.key))
  }

  function advanceObservationCursor(
    previousCursor: SharedObservationCursor | undefined,
    sourceItems: NotificationCenterItem[],
  ): SharedObservationCursor | undefined {
    if (!sourceItems.length) return previousCursor
    const newestTimestamp = Math.max(...sourceItems.map((item) => notificationTimestamp(item.createdAt)))
    if (previousCursor && previousCursor.timestamp > newestTimestamp) return previousCursor
    const timestamp = Math.max(previousCursor?.timestamp ?? 0, newestTimestamp)
    if (previousCursor?.timestamp === timestamp && previousCursor.saturated) return previousCursor
    const boundaryKeys = new Set(
      previousCursor?.timestamp === timestamp ? previousCursor.boundaryKeys : [],
    )
    sourceItems.forEach((item) => {
      if (notificationTimestamp(item.createdAt) === timestamp) boundaryKeys.add(item.key)
    })
    const saturated = boundaryKeys.size > MAX_WATERMARK_BOUNDARY_KEYS
    return {
      timestamp,
      boundaryKeys: saturated ? [] : [...boundaryKeys],
      saturated,
    }
  }

  function updateObservationCursors(
    cursors: SharedObservationWatermarks,
    sourceItems: NotificationCenterItem[],
  ) {
    ;(['molding', 'system'] as NotificationCenterSource[]).forEach((source) => {
      const nextCursor = advanceObservationCursor(
        cursors[source],
        sourceItems.filter((item) => item.source === source),
      )
      if (nextCursor) cursors[source] = nextCursor
    })
  }

  function synchronizeSeen(sourceItems: NotificationCenterItem[]) {
    const sharedAnnouncements = readSharedAnnouncements()
    const sharedKeys = new Set(sharedAnnouncements.map((item) => item.key))
    const watermarks = readSharedWatermarks()
    const now = Date.now()
    const chronologicalItems = [...sourceItems]
      .sort((left, right) => notificationTimestamp(left.createdAt) - notificationTimestamp(right.createdAt))
    chronologicalItems.forEach((item) => {
      if (!sharedKeys.has(item.key)) {
        sharedAnnouncements.push({ key: item.key, announcedAt: now })
        sharedKeys.add(item.key)
      }
    })
    updateObservationCursors(watermarks, sourceItems)
    rememberItemsInChronologicalOrder(sourceItems)
    persistSharedAnnouncements(sharedAnnouncements)
    persistSharedWatermarks(watermarks)
  }

  function claimNewItemsWithoutLock(
    sourceItems: NotificationCenterItem[],
    announcementStorageKey: string,
    watermarkStorageKey: string,
  ) {
    const sharedAnnouncements = readSharedAnnouncements(announcementStorageKey)
    const sharedKeys = new Set(sharedAnnouncements.map((item) => item.key))
    const previousWatermarks = readSharedWatermarks(watermarkStorageKey)
    const nextWatermarks = { ...previousWatermarks }
    const now = Date.now()
    const claimedItems: NotificationCenterItem[] = []

    sourceItems.forEach((item) => {
      const alreadySeen = seenNotificationKeys.has(item.key) || sharedKeys.has(item.key)
      const itemTimestamp = notificationTimestamp(item.createdAt)
      const previousCursor = previousWatermarks[item.source]
      const isBeyondCursor = !previousCursor
        || itemTimestamp > previousCursor.timestamp
        || (
          itemTimestamp === previousCursor.timestamp
          && !previousCursor.saturated
          && !previousCursor.boundaryKeys.includes(item.key)
        )
      if (!alreadySeen && isBeyondCursor && item.isUnread) claimedItems.push(item)
    })

    updateObservationCursors(nextWatermarks, sourceItems)
    rememberItemsInChronologicalOrder(sourceItems)
    claimedItems.slice()
      .sort((left, right) => notificationTimestamp(left.createdAt) - notificationTimestamp(right.createdAt))
      .forEach((item) => {
        sharedAnnouncements.push({ key: item.key, announcedAt: now })
        sharedKeys.add(item.key)
      })
    persistSharedAnnouncements(sharedAnnouncements, announcementStorageKey)
    persistSharedWatermarks(nextWatermarks, watermarkStorageKey)
    return claimedItems
  }

  async function claimNewItems(sourceItems: NotificationCenterItem[], requestAccountKey: string) {
    const announcementStorageKey = sharedAnnouncementStorageKey.value
    const watermarkStorageKey = sharedWatermarkStorageKey.value
    const userId = authStore.currentUser?.id || 'anonymous'
    const claimIfCurrent = () => (
      !disposed && requestAccountKey === accountNotificationKey.value
        ? claimNewItemsWithoutLock(sourceItems, announcementStorageKey, watermarkStorageKey)
        : []
    )
    if (typeof navigator === 'undefined') return claimIfCurrent()
    const lockManager = (navigator as Navigator & {
      locks?: { request: <T>(name: string, callback: () => T | Promise<T>) => Promise<T> }
    }).locks
    if (!lockManager?.request) return claimIfCurrent()
    try {
      return await lockManager.request(
        `rr.notification.claim.${userId}`,
        claimIfCurrent,
      )
    } catch {
      return claimIfCurrent()
    }
  }

  function clearToastTimer() {
    if (toastTimer) {
      window.clearTimeout(toastTimer)
      toastTimer = undefined
    }
  }

  function scheduleCurrentToast(duration = toastRemainingMs) {
    clearToastTimer()
    if (disposed || !currentToast.value || isPanelOpen.value) return
    toastRemainingMs = Math.max(250, duration)
    toastExpiresAt = Date.now() + toastRemainingMs
    toastTimer = window.setTimeout(() => dismissCurrentToast(), toastRemainingMs)
  }

  function pauseCurrentToast() {
    if (!toastTimer) return
    toastRemainingMs = Math.max(250, toastExpiresAt - Date.now())
    clearToastTimer()
  }

  function resumeCurrentToast() {
    if (currentToast.value && !toastTimer && !isPanelOpen.value) {
      scheduleCurrentToast(toastRemainingMs)
    }
  }

  function notificationToastEntry(item: NotificationCenterItem): NotificationToastEntry {
    return {
      key: item.key,
      kind: 'notification',
      notification: item,
      title: item.title,
      summary: item.summary,
      categoryLabel: item.categoryLabel,
      contextLabel: item.contextLabel,
      createdAt: item.createdAt,
      route: item.route,
    }
  }

  function summaryToastEntry(sourceItems: NotificationCenterItem[]): NotificationToastEntry {
    const count = sourceItems.length
    return {
      key: `summary:${Date.now()}:${count}`,
      kind: 'summary',
      title: `另有 ${count} 条新消息`,
      summary: '更多新消息已进入通知中心，请打开铃铛集中查看。',
      categoryLabel: '通知汇总',
      contextLabel: `${count} 条待查看`,
      createdAt: new Date().toISOString(),
      route: '',
      notificationKeys: sourceItems.map((item) => item.key),
    }
  }

  function refreshToastEntry(entry: NotificationToastEntry, item: NotificationCenterItem): NotificationToastEntry {
    return {
      ...entry,
      notification: item,
      title: item.title,
      summary: item.summary,
      categoryLabel: item.categoryLabel,
      contextLabel: item.contextLabel,
      createdAt: item.createdAt,
      route: item.route,
    }
  }

  function reconcileToastQueue() {
    if (!toastQueue.value.length) return
    const previousCurrentKey = toastQueue.value[0]?.key
    const latestItems = new Map(items.value.map((item) => [item.key, item]))
    const nextQueue = toastQueue.value.flatMap((entry) => {
      if (!entry.notification) {
        const notificationKeys = (entry.notificationKeys ?? [])
          .filter((key) => latestItems.get(key)?.isUnread)
        if (!notificationKeys.length) return []
        return [{
          ...entry,
          notificationKeys,
          title: `另有 ${notificationKeys.length} 条新消息`,
          summary: '更多新消息已进入通知中心，请打开铃铛集中查看。',
          contextLabel: `${notificationKeys.length} 条待查看`,
        }]
      }
      const latestItem = latestItems.get(entry.notification.key)
      return latestItem?.isUnread ? [refreshToastEntry(entry, latestItem)] : []
    })
    toastQueue.value = nextQueue
    if (previousCurrentKey !== nextQueue[0]?.key) {
      clearToastTimer()
      toastRemainingMs = NOTIFICATION_TOAST_TIMEOUT_MS
      scheduleCurrentToast(toastRemainingMs)
    }
  }

  function enqueueToasts(newItems: NotificationCenterItem[]) {
    if (!newItems.length) return
    const existingKeys = new Set(toastQueue.value.map((item) => item.key))
    const orderedItems = [...newItems]
      .sort((left, right) => {
        const severityDifference = Number(right.severity === 'high') - Number(left.severity === 'high')
        return severityDifference || notificationTimestamp(left.createdAt) - notificationTimestamp(right.createdAt)
      })
    const individualItems = orderedItems.slice(0, 3).map(notificationToastEntry)
    const overflowItems = orderedItems.slice(individualItems.length)
    const appendItems = [
      ...individualItems,
      ...(overflowItems.length ? [summaryToastEntry(overflowItems)] : []),
    ].filter((item) => !existingKeys.has(item.key))
    if (!appendItems.length) return
    const wasEmpty = !toastQueue.value.length
    toastQueue.value = [...toastQueue.value, ...appendItems]
    if (wasEmpty) {
      toastRemainingMs = NOTIFICATION_TOAST_TIMEOUT_MS
      scheduleCurrentToast()
    }
    void playNotificationSound()
  }

  function dismissCurrentToast() {
    clearToastTimer()
    toastQueue.value = toastQueue.value.slice(1)
    toastRemainingMs = NOTIFICATION_TOAST_TIMEOUT_MS
    scheduleCurrentToast(toastRemainingMs)
  }

  function clearToasts() {
    clearToastTimer()
    toastQueue.value = []
    toastRemainingMs = NOTIFICATION_TOAST_TIMEOUT_MS
  }

  function itemsForSources(sources: Set<NotificationCenterSource>) {
    return items.value.filter((item) => sources.has(item.source))
  }

  async function performRefresh(
    reason: NotificationLoadReason,
    onlySource: NotificationCenterSource | undefined,
    requestSequence: number,
    requestAccountKey: string,
  ) {
    const shouldLoadMolding = hasMoldingPermission() && (!onlySource || onlySource === 'molding')
    const shouldLoadSystem = hasSystemPermission() && (!onlySource || onlySource === 'system')
    const requestedSources = Number(shouldLoadMolding) + Number(shouldLoadSystem)

    if (shouldLoadMolding) updateSourceStatus('molding', { state: 'loading', error: '' })
    else if (!onlySource && !hasMoldingPermission()) {
      moldingNotifications.value = []
      updateSourceStatus('molding', { state: 'idle', error: '' })
    }
    if (shouldLoadSystem) updateSourceStatus('system', { state: 'loading', error: '' })
    else if (!onlySource && !hasSystemPermission()) {
      systemNotifications.value = []
      updateSourceStatus('system', { state: 'idle', error: '' })
    }

    if (!requestedSources) return true

    const changeFilters = reason === 'background-poll'
      ? { changed_after: new Date(Date.now() - NOTIFICATION_CHANGE_LOOKBACK_MS).toISOString() }
      : undefined

    const [moldingResult, systemResult] = await Promise.allSettled([
      shouldLoadMolding
        ? (changeFilters ? moldingSampleApi.listNotifications(changeFilters) : moldingSampleApi.listNotifications())
        : Promise.resolve<MoldingSampleNotificationResponse[]>([]),
      shouldLoadSystem
        ? (changeFilters ? systemApi.listNotifications(changeFilters) : systemApi.listNotifications())
        : Promise.resolve<SystemNotificationResponse[]>([]),
    ])
    if (disposed || requestSequence !== loadSequence || requestAccountKey !== accountNotificationKey.value) return false

    const successfulSources = new Set<NotificationCenterSource>()
    if (shouldLoadMolding) {
      if (moldingResult.status === 'fulfilled') {
        const nextMoldingNotifications = reason === 'background-poll'
          ? mergeNotificationsById(moldingNotifications.value, moldingResult.value)
          : moldingResult.value
        moldingNotifications.value = applyReadOverridesToMolding(nextMoldingNotifications)
        updateSourceStatus('molding', { state: 'ready', error: '' })
        successfulSources.add('molding')
      } else {
        updateSourceStatus('molding', { state: 'error', error: getApiErrorMessage(moldingResult.reason) })
      }
    }
    if (shouldLoadSystem) {
      if (systemResult.status === 'fulfilled') {
        const nextSystemNotifications = reason === 'background-poll'
          ? mergeNotificationsById(systemNotifications.value, systemResult.value)
          : systemResult.value
        systemNotifications.value = applyReadOverridesToSystem(nextSystemNotifications)
        updateSourceStatus('system', { state: 'ready', error: '' })
        successfulSources.add('system')
      } else {
        updateSourceStatus('system', { state: 'error', error: getApiErrorMessage(systemResult.reason) })
      }
    }

    reconcileToastQueue()

    const successfulItems = itemsForSources(successfulSources)
    const firstSuccessfulSources = new Set(
      [...successfulSources].filter((source) => !initializedSources.has(source)),
    )
    firstSuccessfulSources.forEach((source) => initializedSources.add(source))

    if (reason !== 'background-poll') {
      synchronizeSeen(successfulItems)
      return successfulSources.size === requestedSources
    }

    if (firstSuccessfulSources.size) synchronizeSeen(itemsForSources(firstSuccessfulSources))
    const announceableSources = new Set(
      [...successfulSources].filter((source) => !firstSuccessfulSources.has(source)),
    )
    const newItems = await claimNewItems(itemsForSources(announceableSources), requestAccountKey)
    if (disposed || requestSequence !== loadSequence || requestAccountKey !== accountNotificationKey.value) return false
    if (isPanelOpen.value) {
      newWhilePanelOpenCount.value += newItems.length
    } else {
      enqueueToasts(newItems)
    }
    return successfulSources.size === requestedSources
  }

  async function refreshNotifications(
    reason: NotificationLoadReason = 'manual-refresh',
    onlySource?: NotificationCenterSource,
  ) {
    if (disposed) return false
    const requestAccountKey = accountNotificationKey.value
    if (activeLoadPromise && activeLoadAccountKey === requestAccountKey) return activeLoadPromise

    const requestSequence = ++loadSequence
    const loadPromise = performRefresh(reason, onlySource, requestSequence, requestAccountKey)
    activeLoadPromise = loadPromise
    activeLoadAccountKey = requestAccountKey
    try {
      return await loadPromise
    } finally {
      if (activeLoadPromise === loadPromise) {
        activeLoadPromise = undefined
        activeLoadAccountKey = ''
      }
    }
  }

  function closePanel(returnFocus = false) {
    isPanelOpen.value = false
    newWhilePanelOpenCount.value = 0
    if (returnFocus) window.setTimeout(() => bellButtonRef.value?.focus(), 0)
  }

  function togglePanel() {
    void unlockSound()
    if (isPanelOpen.value) {
      closePanel()
      return
    }
    isPanelOpen.value = true
    void refreshNotifications('panel-open')
  }

  function markNotificationRead(item: NotificationCenterItem) {
    const latestItem = items.value.find((candidate) => candidate.key === item.key)
    if (!latestItem || latestItem.status !== 'unread') {
      reconcileToastQueue()
      return true
    }
    item = latestItem
    const mutationAccountKey = accountNotificationKey.value
    const mutationKey = readOverrideKey(item.key, mutationAccountKey)
    const existingPromise = readMutationPromises.get(mutationKey)
    if (existingPromise) return existingPromise
    rememberKey(readOverrides, mutationKey)

    const mutationPromise = (async () => {
      if (item.source === 'molding') {
        const previousItem = moldingNotifications.value.find((notification) => notification.id === item.id)
        moldingNotifications.value = moldingNotifications.value.map((notification) => notification.id === item.id
          ? { ...notification, status: '已读', read_at: notification.read_at || new Date().toISOString() }
          : notification)
        reconcileToastQueue()
        try {
          await moldingSampleApi.updateNotification(item.id, { status: '已读' })
          return true
        } catch (error) {
          readOverrides.delete(mutationKey)
          if (mutationAccountKey === accountNotificationKey.value) {
            moldingNotifications.value = moldingNotifications.value.map((notification) => (
              notification.id === item.id && notification.status === '已读' && previousItem
                ? previousItem
                : notification
            ))
            reconcileToastQueue()
            updateSourceStatus('molding', { state: 'error', error: getApiErrorMessage(error) })
          }
          return false
        }
      }

      const previousItem = systemNotifications.value.find((notification) => notification.id === item.id)
      systemNotifications.value = systemNotifications.value.map((notification) => notification.id === item.id
        ? { ...notification, status: 'read', read_at: notification.read_at || new Date().toISOString() }
        : notification)
      reconcileToastQueue()
      try {
        await systemApi.updateNotification(item.id, { status: 'read' })
        return true
      } catch (error) {
        readOverrides.delete(mutationKey)
        if (mutationAccountKey === accountNotificationKey.value) {
          systemNotifications.value = systemNotifications.value.map((notification) => (
            notification.id === item.id && notification.status === 'read' && previousItem
              ? previousItem
              : notification
          ))
          reconcileToastQueue()
          updateSourceStatus('system', { state: 'error', error: getApiErrorMessage(error) })
        }
        return false
      }
    })()
    readMutationPromises.set(mutationKey, mutationPromise)
    void mutationPromise.finally(() => {
      if (readMutationPromises.get(mutationKey) === mutationPromise) readMutationPromises.delete(mutationKey)
    })
    return mutationPromise
  }

  function activateNotification(item: NotificationCenterItem) {
    closePanel()
    const latestItem = items.value.find((candidate) => candidate.key === item.key)
    toastQueue.value = toastQueue.value.filter((entry) => entry.notification?.key !== item.key)
    clearToastTimer()
    toastRemainingMs = NOTIFICATION_TOAST_TIMEOUT_MS
    scheduleCurrentToast(toastRemainingMs)
    if (latestItem) void markNotificationRead(latestItem)
  }

  function activateToast(entry: NotificationToastEntry) {
    if (entry.notification) {
      activateNotification(entry.notification)
      return
    }
    dismissCurrentToast()
    isPanelOpen.value = true
    void refreshNotifications('panel-open')
  }

  function closePanelOnOutsidePointer(event: PointerEvent) {
    if (!isPanelOpen.value || !popoverRef.value) return
    const eventPath = event.composedPath()
    if (!eventPath.includes(popoverRef.value) && (!panelRef.value || !eventPath.includes(panelRef.value))) closePanel()
  }

  function closePanelOnEscape(event: KeyboardEvent) {
    if (event.key === 'Escape' && isPanelOpen.value) closePanel(true)
  }

  watch(isPanelOpen, (isOpen) => {
    if (isOpen) pauseCurrentToast()
    else resumeCurrentToast()
  })

  function clearRefreshTimer() {
    if (refreshTimer) {
      window.clearTimeout(refreshTimer)
      refreshTimer = undefined
    }
  }

  function canPoll() {
    return authStore.isAuthenticated
      && document.visibilityState !== 'hidden'
      && navigator.onLine !== false
  }

  function scheduleRefresh(delay = currentPollInterval) {
    clearRefreshTimer()
    if (disposed || !canPoll()) return
    refreshTimer = window.setTimeout(async () => {
      const succeeded = await refreshNotifications('background-poll')
      currentPollInterval = succeeded
        ? NOTIFICATION_REFRESH_INTERVAL_MS
        : Math.min(MAX_NOTIFICATION_REFRESH_INTERVAL_MS, currentPollInterval * 2)
      scheduleRefresh(currentPollInterval)
    }, delay)
  }

  function handleVisibilityChange() {
    clearRefreshTimer()
    if (document.visibilityState === 'visible' && navigator.onLine !== false) {
      void refreshNotifications('visibility-resume').finally(() => scheduleRefresh())
    }
  }

  function handleOnline() {
    currentPollInterval = NOTIFICATION_REFRESH_INTERVAL_MS
    if (document.visibilityState === 'hidden') return
    void refreshNotifications('visibility-resume').finally(() => scheduleRefresh())
  }

  function handleOffline() {
    clearRefreshTimer()
  }

  watch(accountNotificationKey, () => {
    const reason: NotificationLoadReason = hasInitializedAccountContext ? 'account-change' : 'initial'
    hasInitializedAccountContext = true
    loadSequence += 1
    activeLoadPromise = undefined
    activeLoadAccountKey = ''
    moldingNotifications.value = []
    systemNotifications.value = []
    seenNotificationKeys.clear()
    readOverrides.clear()
    initializedSources.clear()
    clearToasts()
    closePanel()
    currentPollInterval = NOTIFICATION_REFRESH_INTERVAL_MS
    void refreshNotifications(reason).finally(() => scheduleRefresh())
  }, { immediate: true })

  onMounted(() => {
    document.addEventListener('pointerdown', closePanelOnOutsidePointer)
    document.addEventListener('keydown', closePanelOnEscape)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    scheduleRefresh()
  })

  onUnmounted(() => {
    disposed = true
    loadSequence += 1
    activeLoadPromise = undefined
    activeLoadAccountKey = ''
    document.removeEventListener('pointerdown', closePanelOnOutsidePointer)
    document.removeEventListener('keydown', closePanelOnEscape)
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
    clearRefreshTimer()
    clearToasts()
  })

  return {
    isPanelOpen,
    bellButtonRef,
    popoverRef,
    panelRef,
    items,
    unreadCount,
    pendingCount,
    currentToast,
    queuedToastCount,
    newWhilePanelOpenCount,
    state,
    isRefreshing,
    sourceErrors,
    soundEnabled,
    soundReady,
    toggleSound,
    previewSound,
    togglePanel,
    closePanel,
    dismissCurrentToast,
    pauseCurrentToast,
    resumeCurrentToast,
    activateNotification,
    markNotificationRead,
    activateToast,
    refreshNotifications,
    formatNotificationTime,
  }
}

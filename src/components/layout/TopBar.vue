<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Bell, Menu, RefreshCw, Search, X } from '@lucide/vue'
import { useRoute } from 'vue-router'
import { factoryContexts } from '@/data/enterpriseMock'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import RouteLoadingBar from '@/components/layout/RouteLoadingBar.vue'
import { moldingSampleApi, type MoldingSampleNotificationResponse } from '@/api/moldingSample'
import { systemApi, type SystemNotificationResponse } from '@/api/system'
import { getApiErrorMessage } from '@/lib/http'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()
const props = withDefaults(defineProps<{
  navigationOpen?: boolean
}>(), {
  navigationOpen: false,
})
const emit = defineEmits<{
  toggleNavigation: []
}>()
const brandLogoSrc = '/brand/huadeng_group_dynamic_logo.svg'
const isNotificationPanelOpen = ref(false)
const navigationTriggerRef = ref<HTMLButtonElement | null>(null)
const notificationPopoverRef = ref<HTMLElement | null>(null)
const notificationState = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const notifications = ref<MoldingSampleNotificationResponse[]>([])
const systemNotifications = ref<SystemNotificationResponse[]>([])
const notificationToast = ref<MoldingSampleNotificationResponse | null>(null)
const notificationError = ref('')
const NOTIFICATION_REFRESH_INTERVAL_MS = 30_000
const NOTIFICATION_TOAST_TIMEOUT_MS = 10_000
let notificationRefreshTimer: ReturnType<typeof window.setInterval> | undefined
let notificationToastTimer: ReturnType<typeof window.setTimeout> | undefined
const seenNotificationIds = new Set<string>()

const searchPlaceholder = computed(() => {
  if (route.path.startsWith('/modules')) return '搜索模块、菜单、角色、权限、流程单'
  if (route.name === 'workbench') return '搜索客户、订单、合同、审批单号'

  return '搜索订单、图纸、BOM、审批单、客户或模块'
})

const topBarFactoryContexts = computed(() => {
  const pinnedFactoryIds = new Set(['group', 'huaxing'])
  const pinnedFactories = ['group', 'huaxing']
    .map((factoryId) => factoryContexts.find((factory) => factory.id === factoryId))
    .filter((factory): factory is (typeof factoryContexts)[number] => Boolean(factory))

  return [
    ...pinnedFactories,
    ...factoryContexts.filter((factory) => !pinnedFactoryIds.has(factory.id)),
  ]
})

const getTopBarFactoryLabel = (factory: (typeof factoryContexts)[number]) => (
  factory.id === 'group' ? '总务' : factory.shortName
)

const accountNotificationKey = computed(() => [
  authStore.currentUser?.id ?? '',
  authStore.roles.join(','),
  authStore.permissions.join(','),
  authStore.factoryScopes.join(','),
].join('|'))

const pendingNotifications = computed(() => getPendingNotificationsForCurrentAccount(notifications.value))
const pendingSystemNotifications = computed(() =>
  systemNotifications.value.filter((notification) => notification.status !== 'handled'),
)

const pendingNotificationCount = computed(() => pendingNotifications.value.length + pendingSystemNotifications.value.length)

function hasNotificationPermission() {
  return authStore.isAuthenticated && authStore.can('molding_sample:notification_read')
}

function hasSystemNotificationPermission() {
  return authStore.isAuthenticated && authStore.can('system:user_manage')
}

function isAdminAccount() {
  return authStore.roles.includes('系统管理员')
    || authStore.can('system:user_manage')
}

function isNotificationFactoryInScope(notification: MoldingSampleNotificationResponse) {
  return getNotificationDepartments(notification).some((department) =>
    authStore.can(
      'molding_sample:notification_read',
      notification.factory_id,
      department,
    ),
  )
}

function getNotificationDepartments(notification: MoldingSampleNotificationResponse) {
  if (notification.target_department) {
    if (['production', 'molding'].includes(notification.target_department)) {
      return ['production', 'molding']
    }
    if (['pmc-warehouse', 'warehouse'].includes(notification.target_department)) {
      return ['pmc-warehouse', 'warehouse']
    }
    return [notification.target_department]
  }

  if (/经理|管理/.test(notification.target_role)) {
    return ['management']
  }
  if (/啤机|生产/.test(notification.target_role)) {
    return ['production', 'molding']
  }
  if (/仓|PMC/.test(notification.target_role)) {
    return ['pmc-warehouse', 'warehouse']
  }
  return ['engineering']
}

function getAccountTargetRoles() {
  const targets = new Set(authStore.roles)
  const roleNames = authStore.roles
  if (
    roleNames.some((role) => role === '工程部' || role.includes('工程师'))
    || authStore.can('molding_sample:create')
  ) {
    targets.add('工程部')
  }
  if (
    roleNames.some((role) => role.includes('工程主管'))
    || authStore.can('molding_sample:supervisor_review')
  ) {
    targets.add('工程主管')
  }
  if (
    roleNames.some((role) => role.includes('经理'))
    || authStore.can('molding_sample:manager_review')
  ) {
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
  if (isAdminAccount()) {
    return true
  }

  return getAccountTargetRoles().has(notification.target_role)
}

function getPendingNotificationsForCurrentAccount(source: MoldingSampleNotificationResponse[]) {
  return source.filter((notification) =>
    notification.status !== '已处理'
    && isNotificationFactoryInScope(notification)
    && isNotificationRoleForCurrentAccount(notification),
  )
}

function getNotificationRoute(notification: MoldingSampleNotificationResponse) {
  const params = new URLSearchParams({
    factory: notification.factory_id,
    order_id: notification.order_id,
  })

  if (notification.target_module === 'production_molding_sample_task') {
    return `/modules/production/molding-sample-tasks?${params.toString()}`
  }

  return `/modules/molding-sample?${params.toString()}`
}

function getSystemNotificationRoute(notification: SystemNotificationResponse) {
  if (notification.type === 'password_reset') {
    return `/system/users?tab=password-reset&notification_id=${encodeURIComponent(notification.id)}`
  }

  const requestId = typeof notification.payload.registration_request_id === 'string'
    ? notification.payload.registration_request_id
    : ''
  return requestId ? `/system/users?request_id=${encodeURIComponent(requestId)}` : '/system/users'
}

function closeNotificationToast() {
  notificationToast.value = null
  if (notificationToastTimer) {
    window.clearTimeout(notificationToastTimer)
    notificationToastTimer = undefined
  }
}

function showNotificationToast(notification: MoldingSampleNotificationResponse) {
  notificationToast.value = notification
  if (notificationToastTimer) {
    window.clearTimeout(notificationToastTimer)
  }

  notificationToastTimer = window.setTimeout(() => {
    if (notificationToast.value?.id === notification.id) {
      notificationToast.value = null
    }
  }, NOTIFICATION_TOAST_TIMEOUT_MS)
}

function announceNewPendingNotification(source: MoldingSampleNotificationResponse[]) {
  const currentPendingNotifications = getPendingNotificationsForCurrentAccount(source)
  const newNotification = currentPendingNotifications.find((notification) => !seenNotificationIds.has(notification.id))

  currentPendingNotifications.forEach((notification) => {
    seenNotificationIds.add(notification.id)
  })

  if (newNotification) {
    showNotificationToast(newNotification)
  }
}

function markNotificationHandledLocally(notificationId: string) {
  notifications.value = notifications.value.map((notification) =>
    notification.id === notificationId
      ? { ...notification, status: '已处理' }
      : notification,
  )
}

async function markNotificationHandled(notification: MoldingSampleNotificationResponse) {
  closeNotificationToast()
  isNotificationPanelOpen.value = false
  markNotificationHandledLocally(notification.id)

  try {
    await moldingSampleApi.updateNotification(notification.id, { status: '已处理' })
  }
  catch (error) {
    notificationError.value = getApiErrorMessage(error)
  }
}

function closeNotificationPanelOnOutsidePointer(event: PointerEvent) {
  if (!isNotificationPanelOpen.value || !notificationPopoverRef.value) {
    return
  }

  if (!event.composedPath().includes(notificationPopoverRef.value)) {
    isNotificationPanelOpen.value = false
  }
}

function closeNotificationPanelOnEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    isNotificationPanelOpen.value = false
  }
}

async function markSystemNotificationRead(notification: SystemNotificationResponse) {
  closeNotificationToast()
  isNotificationPanelOpen.value = false
  systemNotifications.value = systemNotifications.value.map((item) =>
    item.id === notification.id
      ? { ...item, status: 'read', read_at: item.read_at || new Date().toISOString() }
      : item,
  )

  try {
    await systemApi.updateNotification(notification.id, { status: 'read' })
  }
  catch (error) {
    notificationError.value = getApiErrorMessage(error)
  }
}

async function loadAccountNotifications() {
  const shouldLoadMoldingNotifications = hasNotificationPermission()
  const shouldLoadSystemNotifications = hasSystemNotificationPermission()

  if (!shouldLoadMoldingNotifications && !shouldLoadSystemNotifications) {
    notifications.value = []
    systemNotifications.value = []
    notificationState.value = 'idle'
    notificationError.value = ''
    seenNotificationIds.clear()
    closeNotificationToast()
    return
  }

  if (!notifications.value.length && !systemNotifications.value.length) {
    notificationState.value = 'loading'
  }
  notificationError.value = ''

  try {
    const [loadedNotifications, loadedSystemNotifications] = await Promise.all([
      shouldLoadMoldingNotifications ? moldingSampleApi.listNotifications() : Promise.resolve([]),
      shouldLoadSystemNotifications ? systemApi.listNotifications() : Promise.resolve([]),
    ])
    notifications.value = loadedNotifications
    systemNotifications.value = loadedSystemNotifications
    notificationState.value = 'ready'
    announceNewPendingNotification(loadedNotifications)
  }
  catch (error) {
    notifications.value = []
    systemNotifications.value = []
    notificationState.value = 'error'
    notificationError.value = getApiErrorMessage(error)
  }
}

watch(accountNotificationKey, () => {
  seenNotificationIds.clear()
  closeNotificationToast()
  void loadAccountNotifications()
}, { immediate: true })

watch(isNotificationPanelOpen, (isOpen) => {
  if (isOpen) {
    void loadAccountNotifications()
  }
})

watch(() => props.navigationOpen, (isOpen, wasOpen) => {
  if (wasOpen && !isOpen) {
    void nextTick(() => navigationTriggerRef.value?.focus())
  }
})

onMounted(() => {
  document.addEventListener('pointerdown', closeNotificationPanelOnOutsidePointer)
  document.addEventListener('keydown', closeNotificationPanelOnEscape)
  notificationRefreshTimer = window.setInterval(() => {
    void loadAccountNotifications()
  }, NOTIFICATION_REFRESH_INTERVAL_MS)
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', closeNotificationPanelOnOutsidePointer)
  document.removeEventListener('keydown', closeNotificationPanelOnEscape)
  if (notificationRefreshTimer) {
    window.clearInterval(notificationRefreshTimer)
  }
  closeNotificationToast()
})
</script>

<template>
  <header class="sticky top-0 z-40 h-auto border-b border-slate-200/80 bg-white/90 shadow-[0_1px_2px_rgba(15,23,42,0.04)] backdrop-blur-xl">
    <div class="flex min-h-[72px] items-center gap-2.5 px-3 sm:gap-3 sm:px-4 2xl:gap-5 2xl:px-6">
      <button
        ref="navigationTriggerRef"
        type="button"
        class="flex size-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/25 lg:hidden"
        aria-label="打开全局导航"
        aria-controls="global-navigation"
        :aria-expanded="props.navigationOpen"
        @click="emit('toggleNavigation')"
      >
        <Menu class="size-4.5" aria-hidden="true" />
      </button>

      <RouterLink to="/" class="flex min-w-0 items-center gap-3 sm:min-w-[200px] 2xl:min-w-[236px]">
        <span class="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-lg">
          <img
            :src="brandLogoSrc"
            alt="Huadeng Group logo"
            class="h-full w-full object-contain"
          >
        </span>
        <span class="hidden min-w-0 sm:block">
          <span class="block truncate text-base font-semibold text-slate-950">Royal Regent Nexus</span>
          <span class="block truncate text-xs text-slate-500">{{ appStore.activeFactory.description }}</span>
        </span>
      </RouterLink>

      <div class="hidden h-9 min-w-[220px] max-w-xl flex-1 items-center gap-2 rounded-lg border border-slate-200/90 bg-slate-50/75 px-3 shadow-[inset_0_1px_2px_rgba(15,23,42,0.03)] transition-colors hover:border-slate-300 hover:bg-white lg:flex">
        <Search class="size-4 shrink-0 text-slate-400" aria-hidden="true" />
        <span class="truncate text-sm text-slate-500">{{ searchPlaceholder }}</span>
      </div>

      <div class="ml-auto hidden min-w-0 max-w-[40vw] items-center overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden xl:flex">
        <div class="flex min-w-max items-center gap-1.5 pr-1">
          <button
            v-for="factory in topBarFactoryContexts"
            :key="factory.id"
            type="button"
            class="h-9 shrink-0 rounded-lg border px-3 text-xs font-semibold transition-[color,background-color,border-color,box-shadow,transform] duration-150 active:translate-y-px 2xl:px-4 2xl:text-sm"
            :class="factory.id === appStore.activeFactoryId
              ? 'border-teal-700 bg-teal-700 text-white shadow-[0_5px_14px_-9px_rgba(13,148,136,0.9)]'
              : 'border-slate-200 bg-white/85 text-slate-600 hover:border-teal-200 hover:bg-teal-50/60 hover:text-teal-800'"
            :aria-label="`切换至${getTopBarFactoryLabel(factory)}`"
            :title="factory.name"
            @click="appStore.setActiveFactory(factory.id)"
          >
            {{ getTopBarFactoryLabel(factory) }}
          </button>
        </div>
      </div>

      <div ref="notificationPopoverRef" class="relative">
        <button
          type="button"
          class="relative flex size-9 items-center justify-center rounded-lg border bg-white shadow-sm transition"
          :class="pendingNotificationCount ? 'border-teal-200 text-teal-700 hover:bg-teal-50' : 'border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-950'"
          aria-label="未处理项通知"
          :aria-expanded="isNotificationPanelOpen"
          @click="isNotificationPanelOpen = !isNotificationPanelOpen"
        >
          <Bell class="size-4" aria-hidden="true" />
          <span
            v-if="pendingNotificationCount"
            class="absolute -right-1 -top-1 flex min-w-5 items-center justify-center rounded-full border-2 border-white bg-teal-600 px-1 text-[10px] font-bold leading-4 text-white shadow-sm"
          >
            {{ pendingNotificationCount > 99 ? '99+' : pendingNotificationCount }}
          </span>
        </button>

        <Transition name="popover">
          <section
            v-if="isNotificationPanelOpen"
            class="fixed left-3 right-3 top-[68px] z-50 w-auto max-w-none origin-top overflow-hidden rounded-xl border border-slate-200 bg-white/98 shadow-2xl shadow-slate-950/12 backdrop-blur-xl sm:absolute sm:left-auto sm:right-0 sm:top-12 sm:w-[calc(100vw-1.5rem)] sm:max-w-[380px] sm:origin-top-right"
            aria-label="未处理项通知面板"
          >
          <div class="flex items-start justify-between gap-3 border-b border-slate-100 px-4 py-3">
            <div>
              <h2 class="text-sm font-bold text-slate-950">未处理项通知</h2>
              <p class="mt-0.5 text-[11px] text-slate-500">
                {{ authStore.currentUser?.display_name ?? '当前账号' }} · {{ pendingNotificationCount }} 项
              </p>
            </div>
            <button
              type="button"
              class="flex size-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:text-slate-300"
              :disabled="notificationState === 'loading'"
              aria-label="刷新未处理项通知"
              @click="loadAccountNotifications"
            >
              <RefreshCw class="size-3.5" aria-hidden="true" />
            </button>
          </div>

          <div class="max-h-[420px] overflow-y-auto p-2">
            <div v-if="notificationState === 'loading'" class="rounded-lg bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">
              正在读取未处理项...
            </div>
            <div v-else-if="notificationState === 'error'" class="rounded-lg border border-red-100 bg-red-50 px-3 py-3 text-sm text-red-700">
              通知读取失败：{{ notificationError }}
            </div>
            <div v-else-if="!pendingNotifications.length && !pendingSystemNotifications.length" class="rounded-lg bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">
              当前账号暂无未处理项。
            </div>
            <div v-else class="space-y-2">
              <div v-if="pendingSystemNotifications.length" class="space-y-2">
                <p class="px-1 text-[11px] font-bold text-slate-500">系统通知</p>
                <RouterLink
                  v-for="notification in pendingSystemNotifications"
                  :key="notification.id"
                  :to="getSystemNotificationRoute(notification)"
                  class="block rounded-lg border border-teal-100 bg-teal-50/60 px-3 py-2.5 text-left transition hover:border-teal-200 hover:bg-teal-50"
                  @click="markSystemNotificationRead(notification)"
                >
                  <div class="flex items-start justify-between gap-2">
                    <span class="min-w-0 truncate text-[13px] font-bold text-slate-950">{{ notification.title }}</span>
                    <span class="shrink-0 rounded-full bg-teal-100 px-1.5 py-0.5 text-[10px] font-bold text-teal-700">
                      {{ notification.status === 'read' ? '已读' : '未读' }}
                    </span>
                  </div>
                  <div class="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-500">
                    <span>{{ notification.type }}</span>
                    <span>{{ notification.created_at }}</span>
                  </div>
                  <p class="mt-1 line-clamp-2 text-[11px] leading-5 text-slate-600">{{ notification.message }}</p>
                </RouterLink>
              </div>
              <RouterLink
                v-for="notification in pendingNotifications"
                :key="notification.id"
                :to="getNotificationRoute(notification)"
                class="block rounded-lg border border-slate-100 bg-white px-3 py-2.5 text-left transition hover:border-teal-200 hover:bg-teal-50/50"
                @click="markNotificationHandled(notification)"
              >
                <div class="flex items-start justify-between gap-2">
                  <span class="min-w-0 truncate text-[13px] font-bold text-slate-950">{{ notification.title }}</span>
                  <span class="shrink-0 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-700">{{ notification.status }}</span>
                </div>
                <div class="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-500">
                  <span class="font-mono">{{ notification.order_id }}</span>
                  <span>{{ notification.target_role }}</span>
                  <span>{{ notification.created_at }}</span>
                </div>
                <p class="mt-1 line-clamp-2 text-[11px] leading-5 text-slate-500">{{ notification.message }}</p>
              </RouterLink>
            </div>
          </div>
          </section>
        </Transition>
      </div>

      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="translate-y-2 scale-95 opacity-0"
        enter-to-class="translate-y-0 scale-100 opacity-100"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="translate-y-0 scale-100 opacity-100"
        leave-to-class="translate-y-2 scale-95 opacity-0"
      >
        <div
          v-if="notificationToast"
          :key="notificationToast.id"
          class="fixed right-3 top-20 z-50 w-[calc(100vw-1.5rem)] max-w-[360px] overflow-hidden rounded-xl border border-teal-200 bg-white shadow-2xl shadow-teal-950/10 sm:right-6"
          role="status"
          aria-live="polite"
        >
          <div class="flex items-start gap-3 p-3">
            <div class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-teal-50 text-teal-700">
              <Bell class="size-4" aria-hidden="true" />
            </div>
            <RouterLink
              :to="getNotificationRoute(notificationToast)"
              class="min-w-0 flex-1 text-left"
              @click="markNotificationHandled(notificationToast)"
            >
              <span class="block text-[11px] font-bold text-teal-700">新待办通知</span>
              <span class="mt-0.5 block truncate text-sm font-bold text-slate-950">{{ notificationToast.title }}</span>
              <span class="mt-1 block truncate text-[12px] text-slate-500">
                {{ notificationToast.order_id }} · {{ notificationToast.target_role }}
              </span>
              <span class="mt-1 line-clamp-2 block text-[12px] leading-5 text-slate-600">{{ notificationToast.message }}</span>
            </RouterLink>
            <button
              type="button"
              class="flex size-7 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label="关闭未处理项提示"
              @click="closeNotificationToast"
            >
              <X class="size-3.5" aria-hidden="true" />
            </button>
          </div>
        </div>
      </Transition>

      <AccountMenu />
    </div>
    <RouteLoadingBar />
  </header>
</template>

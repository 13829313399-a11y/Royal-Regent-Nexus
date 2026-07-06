<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Bell, RefreshCw, Search, X } from '@lucide/vue'
import { useRoute } from 'vue-router'
import { factoryContexts } from '@/data/enterpriseMock'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import RouteLoadingBar from '@/components/layout/RouteLoadingBar.vue'
import { moldingSampleApi, type MoldingSampleNotificationResponse } from '@/api/moldingSample'
import { getApiErrorMessage } from '@/lib/http'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()
const brandLogoSrc = '/brand/huadeng_group_dynamic_logo.svg'
const isNotificationPanelOpen = ref(false)
const notificationState = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const notifications = ref<MoldingSampleNotificationResponse[]>([])
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

const pendingNotificationCount = computed(() => pendingNotifications.value.length)

function hasNotificationPermission() {
  return authStore.isAuthenticated && authStore.hasPermission('molding_sample:notification_read')
}

function isAdminAccount() {
  return authStore.roles.includes('系统管理员')
    || authStore.permissions.includes('system:user_manage')
    || authStore.factoryScopes.includes('*')
}

function isNotificationFactoryInScope(notification: MoldingSampleNotificationResponse) {
  return authStore.factoryScopes.includes('*') || authStore.factoryScopes.includes(notification.factory_id)
}

function getAccountTargetRoles() {
  const targets = new Set(authStore.roles)
  const roleNames = authStore.roles
  const permissionText = authStore.permissions.join(',')

  if (
    roleNames.some((role) => role === '工程部' || role.includes('工程师'))
    || /molding_sample:create/.test(permissionText)
  ) {
    targets.add('工程部')
  }
  if (
    roleNames.some((role) => role.includes('工程主管'))
    || /molding_sample:supervisor_review/.test(permissionText)
  ) {
    targets.add('工程主管')
  }
  if (
    roleNames.some((role) => role.includes('经理'))
    || /molding_sample:manager_review/.test(permissionText)
  ) {
    targets.add('经理')
  }
  if (roleNames.some((role) => role.includes('啤机')) || /molding_sample:production_/.test(permissionText)) {
    targets.add('啤机部')
  }
  if (roleNames.some((role) => /仓|PMC/.test(role)) || /molding_sample:(warehouse_requisition|inventory_issue)/.test(permissionText)) {
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

async function loadAccountNotifications() {
  if (!hasNotificationPermission()) {
    notifications.value = []
    notificationState.value = 'idle'
    notificationError.value = ''
    seenNotificationIds.clear()
    closeNotificationToast()
    return
  }

  notificationState.value = 'loading'
  notificationError.value = ''

  try {
    const loadedNotifications = await moldingSampleApi.listNotifications()
    notifications.value = loadedNotifications
    notificationState.value = 'ready'
    announceNewPendingNotification(loadedNotifications)
  }
  catch (error) {
    notifications.value = []
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

onMounted(() => {
  notificationRefreshTimer = window.setInterval(() => {
    void loadAccountNotifications()
  }, NOTIFICATION_REFRESH_INTERVAL_MS)
})

onUnmounted(() => {
  if (notificationRefreshTimer) {
    window.clearInterval(notificationRefreshTimer)
  }
  closeNotificationToast()
})
</script>

<template>
  <header class="sticky top-0 z-30 h-auto border-b border-slate-200 bg-white/95 backdrop-blur">
    <div class="flex min-h-[72px] items-center gap-5 px-6">
      <RouterLink to="/" class="flex min-w-[236px] items-center gap-3">
        <span class="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-lg">
          <img
            :src="brandLogoSrc"
            alt="Huadeng Group logo"
            class="h-full w-full object-contain"
          >
        </span>
        <span class="min-w-0">
          <span class="block truncate text-base font-semibold text-slate-950">Royal Regent Nexus</span>
          <span class="block truncate text-xs text-slate-500">{{ appStore.activeFactory.description }}</span>
        </span>
      </RouterLink>

      <div class="hidden h-9 min-w-[260px] max-w-xl flex-1 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 lg:flex">
        <Search class="size-4 shrink-0 text-slate-400" aria-hidden="true" />
        <span class="truncate text-sm text-slate-500">{{ searchPlaceholder }}</span>
      </div>

      <div class="ml-auto hidden items-center gap-2 xl:flex">
        <button
          v-for="factory in topBarFactoryContexts"
          :key="factory.id"
          type="button"
          class="h-9 rounded-lg border px-5 text-sm font-semibold transition-colors"
          :class="factory.id === appStore.activeFactoryId
            ? 'border-teal-700 bg-teal-700 text-white'
            : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'"
          @click="appStore.setActiveFactory(factory.id)"
        >
          {{ getTopBarFactoryLabel(factory) }}
        </button>
      </div>

      <div class="relative">
        <button
          type="button"
          class="relative flex size-9 items-center justify-center rounded-full border bg-slate-50 transition"
          :class="pendingNotificationCount ? 'border-blue-300 text-blue-700 hover:bg-blue-50' : 'border-slate-200 text-slate-500 hover:text-slate-950'"
          aria-label="未处理项通知"
          :aria-expanded="isNotificationPanelOpen"
          @click="isNotificationPanelOpen = !isNotificationPanelOpen"
        >
          <Bell class="size-4" aria-hidden="true" />
          <span
            v-if="pendingNotificationCount"
            class="absolute -right-1 -top-1 flex min-w-5 items-center justify-center rounded-full border-2 border-white bg-blue-600 px-1 text-[10px] font-bold leading-4 text-white"
          >
            {{ pendingNotificationCount > 99 ? '99+' : pendingNotificationCount }}
          </span>
        </button>

        <section
          v-if="isNotificationPanelOpen"
          class="absolute right-0 top-12 z-50 w-[380px] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"
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
            <div v-else-if="!pendingNotifications.length" class="rounded-lg bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">
              当前账号暂无未处理项。
            </div>
            <div v-else class="space-y-2">
              <RouterLink
                v-for="notification in pendingNotifications"
                :key="notification.id"
                :to="getNotificationRoute(notification)"
                class="block rounded-lg border border-slate-100 bg-white px-3 py-2.5 text-left transition hover:border-blue-200 hover:bg-blue-50/50"
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
          class="fixed right-6 top-20 z-50 w-[360px] overflow-hidden rounded-xl border border-blue-200 bg-white shadow-2xl shadow-blue-950/10"
          role="status"
          aria-live="polite"
        >
          <div class="flex items-start gap-3 p-3">
            <div class="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-700">
              <Bell class="size-4" aria-hidden="true" />
            </div>
            <RouterLink
              :to="getNotificationRoute(notificationToast)"
              class="min-w-0 flex-1 text-left"
              @click="markNotificationHandled(notificationToast)"
            >
              <span class="block text-[11px] font-bold text-blue-700">新待办通知</span>
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

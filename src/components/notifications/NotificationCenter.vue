<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  AlertTriangle,
  Bell,
  Check,
  ExternalLink,
  RefreshCw,
  Volume2,
  VolumeX,
  X,
} from '@lucide/vue'
import NotificationToastHost from '@/components/notifications/NotificationToastHost.vue'
import {
  type NotificationCenterItem,
  type NotificationCenterSource,
  useNotificationCenter,
} from '@/composables/useNotificationCenter'

type NotificationTab = 'all' | 'pending' | 'system'

const {
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
  markNotificationHandled,
  activateToast,
  refreshNotifications,
  formatNotificationTime,
} = useNotificationCenter()

const activeTab = ref<NotificationTab>('all')
const panelStyle = ref<Record<string, string>>({})
const panelHeadingRef = ref<HTMLElement | null>(null)

const tabs = computed(() => [
  { key: 'all' as const, label: '全部', count: items.value.length },
  { key: 'pending' as const, label: '待处理', count: pendingCount.value },
  { key: 'system' as const, label: '系统消息', count: items.value.filter((item) => item.source === 'system').length },
])

const visibleItems = computed(() => {
  if (activeTab.value === 'pending') return items.value.filter((item) => item.isPending)
  if (activeTab.value === 'system') return items.value.filter((item) => item.source === 'system')
  return items.value
})

function itemStatusLabel(item: NotificationCenterItem) {
  if (item.status === 'handled') return '已处理'
  if (item.isUnread) return '未读'
  if (item.isPending) return '待处理'
  return '已读'
}

function itemStatusClass(item: NotificationCenterItem) {
  if (item.status === 'handled') return 'text-emerald-700'
  if (item.isUnread) return 'text-teal-700'
  if (item.isPending) return 'text-amber-700'
  return 'text-slate-400'
}

function itemFooterLabel(item: NotificationCenterItem) {
  if (item.status === 'handled') return '业务流程已完成'
  if (item.isPending) return '待业务流程处理'
  return '已查看'
}

function updatePanelPosition() {
  const trigger = bellButtonRef.value
  if (!trigger || typeof window === 'undefined') return
  const rect = trigger.getBoundingClientRect()
  const top = Math.min(rect.bottom + 8, window.innerHeight - 96)
  if (window.innerWidth < 640) {
    panelStyle.value = {
      left: '12px',
      right: '12px',
      top: `${top}px`,
      maxHeight: `calc(100dvh - ${top + 12}px)`,
    }
    return
  }
  panelStyle.value = {
    right: `${Math.max(16, window.innerWidth - rect.right)}px`,
    top: `${top}px`,
    width: '430px',
    maxHeight: `calc(100dvh - ${top + 16}px)`,
  }
}

function retrySource(source: NotificationCenterSource) {
  void refreshNotifications('manual-refresh', source)
}

function handleItemAction(item: NotificationCenterItem) {
  activateNotification(item)
}

function handleMarkRead(item: NotificationCenterItem) {
  void markNotificationRead(item)
}

function canAcknowledgeItem(item: NotificationCenterItem) {
  return item.source === 'system'
    && item.category === 'ai_operational_alert'
    && item.status !== 'handled'
}

function handleMarkHandled(item: NotificationCenterItem) {
  void markNotificationHandled(item)
}

function handleTabKeydown(event: KeyboardEvent, tabIndex: number) {
  const lastIndex = tabs.value.length - 1
  let nextIndex = tabIndex
  if (event.key === 'ArrowRight') nextIndex = tabIndex === lastIndex ? 0 : tabIndex + 1
  else if (event.key === 'ArrowLeft') nextIndex = tabIndex === 0 ? lastIndex : tabIndex - 1
  else if (event.key === 'Home') nextIndex = 0
  else if (event.key === 'End') nextIndex = lastIndex
  else return
  event.preventDefault()
  activeTab.value = tabs.value[nextIndex]!.key
  void nextTick(() => document.getElementById(`notification-tab-${activeTab.value}`)?.focus())
}

watch(isPanelOpen, async (open) => {
  if (!open) return
  updatePanelPosition()
  await nextTick()
  panelHeadingRef.value?.focus()
})

onMounted(() => {
  window.addEventListener('resize', updatePanelPosition)
  window.addEventListener('scroll', updatePanelPosition, true)
})

onUnmounted(() => {
  window.removeEventListener('resize', updatePanelPosition)
  window.removeEventListener('scroll', updatePanelPosition, true)
})
</script>

<template>
  <div ref="popoverRef" class="relative">
    <button
      ref="bellButtonRef"
      type="button"
      class="relative flex size-9 items-center justify-center rounded-lg border bg-white shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
      :class="unreadCount
        ? 'border-teal-200 text-teal-700 hover:bg-teal-50'
        : 'border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-950'"
      :aria-label="`通知中心，${unreadCount} 条未读`"
      :aria-expanded="isPanelOpen"
      aria-haspopup="dialog"
      @click="togglePanel"
    >
      <Bell class="size-4" aria-hidden="true" />
      <span
        v-if="unreadCount"
        class="absolute right-0 top-0 flex min-w-[17px] items-center justify-center rounded-full border-2 border-white bg-teal-700 px-0.5 text-[9px] font-bold leading-[13px] text-white shadow-sm"
      >
        {{ unreadCount > 99 ? '99+' : unreadCount }}
      </span>
    </button>

    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="translate-y-1 opacity-0"
        enter-to-class="translate-y-0 opacity-100"
        leave-active-class="transition duration-100 ease-in"
        leave-from-class="translate-y-0 opacity-100"
        leave-to-class="translate-y-1 opacity-0"
      >
        <section
          v-if="isPanelOpen"
          ref="panelRef"
          :style="panelStyle"
          class="fixed z-[70] flex min-h-0 flex-col overflow-hidden rounded-[14px] border border-slate-200 bg-white shadow-[0_24px_70px_-28px_rgba(15,23,42,0.48)] focus:outline-none sm:min-h-[260px]"
          role="dialog"
          aria-modal="false"
          aria-labelledby="notification-center-title"
          tabindex="-1"
        >
          <header class="shrink-0 border-b border-slate-100 px-4 pb-3 pt-4">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <h2
                  id="notification-center-title"
                  ref="panelHeadingRef"
                  class="text-base font-bold tracking-tight text-slate-950 focus:outline-none"
                  tabindex="-1"
                >
                  通知中心
                </h2>
                <p class="mt-0.5 text-xs text-slate-500">
                  {{ unreadCount }} 条未读 · {{ pendingCount }} 项待处理
                </p>
              </div>

              <div class="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  class="flex h-8 items-center gap-1.5 rounded-lg px-2 text-[11px] font-semibold transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
                  :class="soundEnabled ? 'text-teal-700' : 'text-slate-500'"
                  :aria-label="soundEnabled ? (soundReady ? '关闭消息提示音' : '启用消息提示音') : '开启消息提示音'"
                  :aria-pressed="soundEnabled"
                  :title="soundEnabled && !soundReady ? '点击后启用声音，并试听提示音' : undefined"
                  @click="soundEnabled && soundReady ? toggleSound() : (soundEnabled ? previewSound() : toggleSound())"
                >
                  <Volume2 v-if="soundEnabled" class="size-3.5" aria-hidden="true" />
                  <VolumeX v-else class="size-3.5" aria-hidden="true" />
                  <span class="hidden sm:inline">{{ soundEnabled ? (soundReady ? '声音' : '待启用') : '静音' }}</span>
                </button>
                <button
                  v-if="soundEnabled && soundReady"
                  type="button"
                  class="flex size-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
                  aria-label="试听消息提示音"
                  title="试听提示音"
                  @click="previewSound"
                >
                  <Volume2 class="size-3.5" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  class="flex size-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 disabled:cursor-wait disabled:text-slate-300"
                  :disabled="isRefreshing"
                  aria-label="刷新通知"
                  @click="refreshNotifications('manual-refresh')"
                >
                  <RefreshCw class="size-3.5" :class="{ 'animate-spin': isRefreshing }" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  class="flex size-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
                  aria-label="关闭通知中心"
                  @click="closePanel(true)"
                >
                  <X class="size-4" aria-hidden="true" />
                </button>
              </div>
            </div>

            <div v-if="newWhilePanelOpenCount" class="mt-3 rounded-lg border border-teal-100 bg-teal-50 px-3 py-2 text-xs font-medium text-teal-800" aria-live="polite">
              已收到 {{ newWhilePanelOpenCount }} 条新消息，列表已更新。
            </div>

            <div class="mt-3 flex items-center gap-1 rounded-[10px] bg-slate-100 p-1" role="tablist" aria-label="通知筛选">
              <button
                v-for="(tab, tabIndex) in tabs"
                :key="tab.key"
                type="button"
                class="flex min-w-0 flex-1 items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
                :class="activeTab === tab.key ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
                role="tab"
                :id="`notification-tab-${tab.key}`"
                aria-controls="notification-tabpanel"
                :aria-selected="activeTab === tab.key"
                :tabindex="activeTab === tab.key ? 0 : -1"
                @click="activeTab = tab.key"
                @keydown="handleTabKeydown($event, tabIndex)"
              >
                <span class="truncate">{{ tab.label }}</span>
                <span class="text-[10px] text-slate-400">{{ tab.count }}</span>
              </button>
            </div>
          </header>

          <div v-if="sourceErrors.length" class="shrink-0 space-y-1.5 border-b border-slate-100 bg-amber-50/60 p-3">
            <div
              v-for="error in sourceErrors"
              :key="error.source"
              class="flex items-center gap-2 rounded-lg border border-amber-200/70 bg-white px-2.5 py-2 text-[11px] text-amber-900"
            >
              <AlertTriangle class="size-3.5 shrink-0 text-amber-600" aria-hidden="true" />
              <span class="min-w-0 flex-1 truncate">{{ error.label }}暂时读取失败，已保留上次结果。</span>
              <button type="button" class="shrink-0 font-bold text-amber-800 underline-offset-2 hover:underline" @click="retrySource(error.source)">
                重试
              </button>
            </div>
          </div>

          <div
            id="notification-tabpanel"
            class="min-h-0 flex-1 overflow-y-auto p-2.5"
            role="tabpanel"
            :aria-labelledby="`notification-tab-${activeTab}`"
            aria-live="polite"
          >
            <div v-if="state === 'loading'" class="space-y-2" aria-label="正在读取通知">
              <div v-for="index in 3" :key="index" class="animate-pulse rounded-[12px] border border-slate-100 p-3">
                <div class="h-3 w-24 rounded bg-slate-200" />
                <div class="mt-3 h-3 w-4/5 rounded bg-slate-100" />
                <div class="mt-2 h-3 w-3/5 rounded bg-slate-100" />
              </div>
            </div>

            <div v-else-if="!visibleItems.length" class="flex min-h-[220px] flex-col items-center justify-center px-5 text-center">
              <div class="flex size-11 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                <Check class="size-5" aria-hidden="true" />
              </div>
              <p class="mt-3 text-sm font-bold text-slate-900">当前筛选下暂无通知</p>
              <p class="mt-1 text-xs leading-5 text-slate-500">新的业务协作与系统消息会在这里集中呈现。</p>
            </div>

            <div v-else class="space-y-2">
              <article
                v-for="item in visibleItems"
                :key="item.key"
                class="relative overflow-hidden rounded-[12px] border px-3 py-3 transition hover:border-slate-300 hover:shadow-[0_6px_18px_-14px_rgba(15,23,42,0.35)]"
                :class="item.isUnread ? 'border-teal-100 bg-teal-50/35' : 'border-slate-200 bg-white'"
              >
                <span v-if="item.isUnread" class="absolute inset-y-0 left-0 w-[3px] bg-teal-700" aria-hidden="true" />
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-1.5 text-[10px] font-semibold">
                      <span class="rounded-md bg-slate-100 px-1.5 py-0.5 text-slate-600">{{ item.categoryLabel }}</span>
                      <span v-if="item.severity === 'high'" class="rounded-md bg-amber-50 px-1.5 py-0.5 text-amber-700">优先</span>
                      <span :class="itemStatusClass(item)">{{ itemStatusLabel(item) }}</span>
                    </div>
                    <h3 class="mt-1.5 text-[13px] font-bold leading-5 text-slate-950">{{ item.title }}</h3>
                  </div>
                  <time class="shrink-0 text-[10px] text-slate-400">{{ formatNotificationTime(item.createdAt) }}</time>
                </div>

                <p class="mt-1.5 line-clamp-2 text-xs leading-5 text-slate-600">{{ item.summary }}</p>
                <p class="mt-1.5 truncate text-[11px] text-slate-500">{{ item.contextLabel }}</p>

                <div class="mt-2.5 flex items-center justify-between gap-3 border-t border-slate-100 pt-2.5">
                  <div class="flex items-center gap-3">
                    <button
                      v-if="item.isUnread"
                      type="button"
                      class="text-[11px] font-semibold text-slate-500 transition hover:text-teal-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
                      :aria-label="`将“${item.title}”标为已读`"
                      @click="handleMarkRead(item)"
                    >
                      标为已读
                    </button>
                    <button
                      v-if="canAcknowledgeItem(item)"
                      type="button"
                      class="text-[11px] font-bold text-emerald-700 transition hover:text-emerald-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/30"
                      :aria-label="`确认已处理：${item.title}`"
                      @click="handleMarkHandled(item)"
                    >
                      确认已处理
                    </button>
                    <span v-if="!item.isUnread && !canAcknowledgeItem(item)" class="text-[11px] text-slate-400">{{ itemFooterLabel(item) }}</span>
                  </div>

                  <RouterLink
                    :to="item.route"
                    class="inline-flex items-center gap-1 text-[11px] font-bold text-teal-700 transition hover:text-teal-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
                    :aria-label="`${item.actionLabel}：${item.title}`"
                    @click="handleItemAction(item)"
                  >
                    {{ item.actionLabel }}
                    <ExternalLink class="size-3" aria-hidden="true" />
                  </RouterLink>
                </div>
              </article>
            </div>
          </div>
        </section>
      </Transition>

      <Transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="translate-y-2 opacity-0"
        enter-to-class="translate-y-0 opacity-100"
        leave-active-class="transition duration-100 ease-in"
        leave-from-class="translate-y-0 opacity-100"
        leave-to-class="translate-y-2 opacity-0"
      >
        <NotificationToastHost
          v-if="currentToast && !isPanelOpen"
          :key="currentToast.key"
          :entry="currentToast"
          :queued-count="queuedToastCount"
          :format-time="formatNotificationTime"
          @activate="activateToast"
          @dismiss="dismissCurrentToast"
          @pause="pauseCurrentToast"
          @resume="resumeCurrentToast"
        />
      </Transition>
    </Teleport>
  </div>
</template>

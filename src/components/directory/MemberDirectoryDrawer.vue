<script setup lang="ts">
import { ArrowUpRight, Building2, LoaderCircle, Network, Search, X } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import AvatarPreviewDialog from '@/components/directory/AvatarPreviewDialog.vue'
import MemberDirectoryList from '@/components/directory/MemberDirectoryList.vue'
import type { DirectoryMember, PresenceFilter } from '@/api/directory'
import { directoryApi } from '@/api/directory'
import { useDialogFocus } from '@/features/injection-scheduling-v2/composables/useDialogFocus'
import { acquireBodyScrollLock, type BodyScrollLockRelease } from '@/lib/bodyScrollLock'
import { getApiErrorMessage } from '@/lib/http'

const props = withDefaults(defineProps<{
  open: boolean
  currentFactoryId?: string
  currentDepartment?: string
}>(), {
  currentFactoryId: '',
  currentDepartment: '',
})

const emit = defineEmits<{
  close: []
}>()

const POLL_INTERVAL_MS = 45_000
const SEARCH_DEBOUNCE_MS = 250
const drawerRoot = ref<HTMLElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const searchText = ref('')
const queryText = ref('')
const presence = ref<PresenceFilter>('all')
const factoryFilter = ref('')
const departmentFilter = ref('')
const members = ref<DirectoryMember[]>([])
const total = ref(0)
const onlineCount = ref(0)
const loading = ref(false)
const error = ref('')
const stale = ref(false)
const previewMember = ref<DirectoryMember | null>(null)
const presenceOptions = [
  ['all', '全部'],
  ['online', '在线'],
  ['away', '离开'],
  ['offline', '离线'],
] as const
let pollTimer: ReturnType<typeof setTimeout> | null = null
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let releaseScrollLock: BodyScrollLockRelease | null = null
let requestSequence = 0

interface ButtonRipple {
  id: number
  x: number
  y: number
  size: number
}

const ripples = ref<Record<string, ButtonRipple | undefined>>({})
let rippleSequence = 0
const rippleTimers = new Set<ReturnType<typeof setTimeout>>()

const presenceIndex = computed(() => Math.max(0, presenceOptions.findIndex(([value]) => value === presence.value)))
const presenceIndicatorStyle = computed(() => ({
  transform: `translateX(${presenceIndex.value * 100}%)`,
}))
const activeScopeCount = computed(() => Number(Boolean(factoryFilter.value)) + Number(Boolean(departmentFilter.value)))
const activeScopeDescription = computed(() => {
  if (factoryFilter.value && departmentFilter.value) return '已限定当前厂区与当前部门'
  if (factoryFilter.value) return '已限定当前厂区'
  if (departmentFilter.value) return '已限定当前部门'
  return ''
})

const fullDirectoryQuery = computed(() => {
  const query: Record<string, string> = {}
  if (queryText.value) query.q = queryText.value
  if (presence.value !== 'all') query.presence = presence.value
  if (factoryFilter.value) query.factory_id = factoryFilter.value
  if (departmentFilter.value) query.department = departmentFilter.value
  return query
})

useDialogFocus(
  () => props.open,
  drawerRoot,
  {
    onEscape: () => previewMember.value ? (previewMember.value = null) : emit('close'),
    openAnnouncement: '已打开组织成员目录',
    initialFocus: () => searchInput.value,
  },
)

function canPoll() {
  return props.open
    && document.visibilityState === 'visible'
    && navigator.onLine !== false
}

function clearPollTimer() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function schedulePoll() {
  clearPollTimer()
  if (canPoll()) pollTimer = setTimeout(() => void loadMembers(true), POLL_INTERVAL_MS)
}

async function loadMembers(background = false) {
  if (!props.open || (!background && loading.value)) return
  const sequence = ++requestSequence
  if (!background || !members.value.length) loading.value = true
  try {
    const result = await directoryApi.getMembers({
      page: 1,
      page_size: 50,
      q: queryText.value,
      presence: presence.value,
      factory_id: factoryFilter.value,
      department: departmentFilter.value,
    })
    if (sequence !== requestSequence) return
    members.value = result.items
    total.value = result.total
    onlineCount.value = result.state_counts.online
    error.value = ''
    stale.value = false
  } catch (caught) {
    if (sequence !== requestSequence) return
    error.value = getApiErrorMessage(caught)
    stale.value = members.value.length > 0
  } finally {
    if (sequence === requestSequence) {
      loading.value = false
      schedulePoll()
    }
  }
}

function toggleFactory() {
  factoryFilter.value = factoryFilter.value ? '' : props.currentFactoryId
}

function toggleDepartment() {
  departmentFilter.value = departmentFilter.value ? '' : props.currentDepartment
}

function startRipple(event: PointerEvent, key: string) {
  const target = event.currentTarget as HTMLElement | null
  if (!target) return
  const rect = target.getBoundingClientRect()
  const size = Math.max(rect.width, rect.height) * 2.2
  const ripple: ButtonRipple = {
    id: ++rippleSequence,
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
    size,
  }
  ripples.value = { ...ripples.value, [key]: ripple }

  const timer = setTimeout(() => {
    if (ripples.value[key]?.id === ripple.id) {
      const next = { ...ripples.value }
      delete next[key]
      ripples.value = next
    }
    rippleTimers.delete(timer)
  }, 680)
  rippleTimers.add(timer)
}

function rippleStyle(ripple: ButtonRipple) {
  return {
    left: `${ripple.x}px`,
    top: `${ripple.y}px`,
    width: `${ripple.size}px`,
    height: `${ripple.size}px`,
  }
}

function handleVisibilityOrFocus() {
  clearPollTimer()
  if (canPoll()) void loadMembers(true)
}

watch(searchText, (value) => {
  if (debounceTimer !== null) clearTimeout(debounceTimer)
  rippleTimers.forEach((timer) => clearTimeout(timer))
  rippleTimers.clear()
  debounceTimer = setTimeout(() => {
    queryText.value = value.trim()
  }, SEARCH_DEBOUNCE_MS)
})

watch([queryText, presence, factoryFilter, departmentFilter], () => {
  if (props.open) void loadMembers()
})

watch(() => props.open, (open) => {
  if (open) {
    releaseScrollLock ??= acquireBodyScrollLock()
    void loadMembers()
    return
  }
  requestSequence += 1
  clearPollTimer()
  previewMember.value = null
  releaseScrollLock?.()
  releaseScrollLock = null
}, { immediate: true })

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityOrFocus)
  window.addEventListener('focus', handleVisibilityOrFocus)
  window.addEventListener('online', handleVisibilityOrFocus)
  window.addEventListener('offline', clearPollTimer)
})

onBeforeUnmount(() => {
  requestSequence += 1
  clearPollTimer()
  if (debounceTimer !== null) clearTimeout(debounceTimer)
  document.removeEventListener('visibilitychange', handleVisibilityOrFocus)
  window.removeEventListener('focus', handleVisibilityOrFocus)
  window.removeEventListener('online', handleVisibilityOrFocus)
  window.removeEventListener('offline', clearPollTimer)
  releaseScrollLock?.()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="directory-drawer">
      <div
        v-if="open"
        class="directory-backdrop fixed inset-0 z-[80] flex justify-end bg-slate-950/42 backdrop-blur-[3px]"
        role="presentation"
        @click.self="emit('close')"
      >
        <section
          ref="drawerRoot"
          role="dialog"
          aria-modal="true"
          aria-labelledby="member-directory-drawer-title"
          tabindex="-1"
          class="directory-panel flex h-full w-full flex-col outline-none sm:max-w-[500px]"
        >
          <header class="directory-metal-surface relative z-10 border-b border-slate-200/80 px-4 pb-4 pt-5 sm:px-5">
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-teal-700">Organization</p>
                  <Transition name="directory-crossfade" mode="out-in">
                    <span
                      v-if="loading"
                      key="syncing"
                      class="inline-flex items-center gap-1 rounded-full bg-teal-50 px-2 py-1 text-[10px] font-semibold text-teal-700 ring-1 ring-inset ring-teal-200"
                      role="status"
                    >
                      <LoaderCircle class="directory-spin size-3" aria-hidden="true" />
                      同步中
                    </span>
                    <span
                      v-else-if="stale"
                      key="stale"
                      class="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2 py-1 text-[10px] font-semibold text-amber-700 ring-1 ring-inset ring-amber-200"
                      role="status"
                    >
                      <span class="size-1.5 rounded-full bg-amber-500" aria-hidden="true" />
                      显示缓存
                    </span>
                    <span
                      v-else
                      key="synced"
                      class="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-200"
                      role="status"
                    >
                      <span class="directory-live-dot size-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
                      已同步
                    </span>
                  </Transition>
                </div>
                <h2 id="member-directory-drawer-title" class="mt-1.5 text-[22px] font-semibold tracking-[-0.02em] text-slate-950">组织成员</h2>
                <p class="mt-1 flex items-center gap-2 text-xs text-slate-500">
                  <span class="font-semibold text-teal-700">{{ onlineCount }} 人在线</span>
                  <span class="size-1 rounded-full bg-slate-300" aria-hidden="true" />
                  <span>共 {{ total }} 人</span>
                </p>
              </div>
              <button
                type="button"
                aria-label="关闭组织成员目录"
                class="directory-ripple-control relative grid size-9 shrink-0 place-items-center overflow-hidden rounded-xl border border-white/80 bg-white/75 text-slate-500 shadow-[0_5px_14px_-10px_rgba(15,23,42,0.7),inset_0_1px_0_rgba(255,255,255,0.9)] transition-[transform,background-color,border-color,color] hover:border-teal-200 hover:bg-teal-50 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 active:scale-[0.98]"
                @pointerdown="startRipple($event, 'close')"
                @click="emit('close')"
              >
                <X class="size-5" aria-hidden="true" />
                <span
                  v-if="ripples.close"
                  :key="ripples.close.id"
                  class="directory-ripple"
                  :style="rippleStyle(ripples.close)"
                  aria-hidden="true"
                />
              </button>
            </div>

            <label class="directory-search group relative mt-4 block">
              <span class="sr-only">搜索组织成员</span>
              <Transition name="directory-crossfade" mode="out-in">
                <LoaderCircle
                  v-if="loading"
                  key="search-loading"
                  class="directory-spin pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-teal-600"
                  aria-hidden="true"
                />
                <Search
                  v-else
                  key="search-idle"
                  class="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-teal-700"
                  aria-hidden="true"
                />
              </Transition>
              <input
                ref="searchInput"
                v-model="searchText"
                type="search"
                maxlength="64"
                autocomplete="off"
                placeholder="搜索姓名、职位、厂区或部门"
                class="h-12 w-full rounded-2xl border border-slate-300/90 bg-white/85 pl-10 pr-3 text-sm text-slate-900 shadow-[0_8px_22px_-18px_rgba(15,23,42,0.7),inset_0_1px_0_rgba(255,255,255,0.9)] outline-none transition-[border-color,box-shadow,background-color] placeholder:text-slate-400 hover:border-slate-400/80 focus:border-teal-400 focus:bg-white focus:shadow-[0_0_0_3px_rgba(20,184,166,0.12),0_10px_24px_-18px_rgba(13,148,136,0.8),inset_0_1px_0_rgba(255,255,255,1)]"
              >
            </label>

            <div class="directory-segment mt-3 grid grid-cols-4" aria-label="在线状态筛选">
              <span
                data-testid="presence-pill-indicator"
                class="directory-segment-indicator"
                :style="presenceIndicatorStyle"
                aria-hidden="true"
              />
              <button
                v-for="option in presenceOptions"
                :key="option[0]"
                type="button"
                class="directory-ripple-control relative z-10 h-9 overflow-hidden rounded-xl px-2 text-xs font-semibold transition-[color,transform] duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500/35 active:scale-[0.98]"
                :class="presence === option[0] ? 'text-white' : 'text-slate-600 hover:text-slate-900'"
                :aria-pressed="presence === option[0]"
                @pointerdown="startRipple($event, `presence-${option[0]}`)"
                @click="presence = option[0]"
              >
                {{ option[1] }}
                <span
                  v-if="ripples[`presence-${option[0]}`]"
                  :key="ripples[`presence-${option[0]}`]?.id"
                  class="directory-ripple"
                  :style="rippleStyle(ripples[`presence-${option[0]}`]!)"
                  aria-hidden="true"
                />
              </button>
            </div>

            <div class="mt-2.5 flex flex-wrap gap-2" aria-label="成员范围筛选">
              <button
                v-if="currentFactoryId"
                type="button"
                class="directory-scope-chip directory-ripple-control relative inline-flex h-9 items-center gap-1.5 overflow-hidden rounded-xl px-3 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 active:scale-[0.98]"
                :class="factoryFilter ? 'is-active' : ''"
                :aria-pressed="Boolean(factoryFilter)"
                @pointerdown="startRipple($event, 'factory')"
                @click="toggleFactory"
              >
                <Building2 class="size-3.5" aria-hidden="true" />
                当前厂区
                <span
                  v-if="ripples.factory"
                  :key="ripples.factory.id"
                  class="directory-ripple"
                  :style="rippleStyle(ripples.factory)"
                  aria-hidden="true"
                />
              </button>
              <button
                v-if="currentDepartment"
                type="button"
                class="directory-scope-chip directory-ripple-control relative inline-flex h-9 items-center gap-1.5 overflow-hidden rounded-xl px-3 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 active:scale-[0.98]"
                :class="departmentFilter ? 'is-active' : ''"
                :aria-pressed="Boolean(departmentFilter)"
                @pointerdown="startRipple($event, 'department')"
                @click="toggleDepartment"
              >
                <Network class="size-3.5" aria-hidden="true" />
                当前部门
                <span
                  v-if="ripples.department"
                  :key="ripples.department.id"
                  class="directory-ripple"
                  :style="rippleStyle(ripples.department)"
                  aria-hidden="true"
                />
              </button>
            </div>

            <Transition name="directory-accordion">
              <div
                v-if="activeScopeCount"
                class="directory-scope-summary mt-2.5 flex items-center justify-between gap-3 overflow-hidden rounded-xl border border-teal-200/80 bg-teal-50/70 px-3 text-[11px] text-teal-800"
                role="status"
              >
                <span class="inline-flex items-center gap-2 font-semibold">
                  <span class="size-1.5 rounded-full bg-teal-500" aria-hidden="true" />
                  {{ activeScopeDescription }}
                </span>
                <span class="shrink-0 text-teal-600">{{ activeScopeCount }} 项范围</span>
              </div>
            </Transition>
          </header>

          <div class="directory-list-surface sidebar-scrollbar min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">
            <MemberDirectoryList
              :members="members"
              :loading="loading"
              :error="error"
              :stale="stale"
              variant="drawer"
              @retry="loadMembers()"
              @preview="previewMember = $event"
            />
          </div>

          <footer class="directory-footer relative z-10 border-t border-slate-200/80 px-4 py-4 sm:px-5">
            <RouterLink
              :to="{ name: 'people-directory', query: fullDirectoryQuery }"
              class="directory-primary-action directory-ripple-control relative inline-flex h-11 w-full items-center justify-center gap-2 overflow-hidden rounded-xl px-4 text-sm font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/35 focus-visible:ring-offset-2 active:scale-[0.98]"
              @pointerdown="startRipple($event, 'full-directory')"
              @click="emit('close')"
            >
              查看完整成员目录
              <ArrowUpRight class="size-4" aria-hidden="true" />
              <span
                v-if="ripples['full-directory']"
                :key="ripples['full-directory']?.id"
                class="directory-ripple"
                :style="rippleStyle(ripples['full-directory']!)"
                aria-hidden="true"
              />
            </RouterLink>
            <p class="mt-3 rounded-xl bg-white/55 px-3 py-2 text-center text-[10px] leading-4.5 text-slate-500 ring-1 ring-inset ring-white/80">
              “在线/离开/离线”仅表示近期是否连接企业中台，不代表工作状态、岗位出勤或响应承诺。
            </p>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>

  <AvatarPreviewDialog :member="previewMember" @close="previewMember = null" />
</template>

<style scoped>
.directory-backdrop {
  transition: background-color 260ms ease, backdrop-filter 260ms ease;
}

.directory-panel {
  --directory-spring: cubic-bezier(0.16, 1, 0.3, 1);
  border-left: 1px solid rgb(203 213 225 / 82%);
  background:
    linear-gradient(135deg, rgb(248 250 252 / 98%) 0%, rgb(241 245 249 / 96%) 48%, rgb(248 250 252 / 98%) 100%);
  box-shadow: -24px 0 60px -36px rgb(15 23 42 / 75%), inset 1px 0 0 rgb(255 255 255 / 76%);
}

.directory-metal-surface,
.directory-footer {
  background:
    linear-gradient(118deg, rgb(255 255 255 / 96%) 0%, rgb(241 245 249 / 91%) 48%, rgb(255 255 255 / 96%) 100%);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 90%);
}

.directory-list-surface {
  background:
    radial-gradient(circle at 100% 0%, rgb(204 251 241 / 32%), transparent 38%),
    linear-gradient(145deg, rgb(248 250 252 / 72%), rgb(241 245 249 / 88%));
}

.directory-drawer-enter-active,
.directory-drawer-leave-active {
  transition: opacity 260ms ease;
}

.directory-drawer-enter-active .directory-panel,
.directory-drawer-leave-active .directory-panel {
  transition: transform 520ms var(--directory-spring), opacity 280ms ease;
}

.directory-drawer-enter-from,
.directory-drawer-leave-to {
  opacity: 0;
}

.directory-drawer-enter-from .directory-panel,
.directory-drawer-leave-to .directory-panel {
  opacity: 0.72;
  transform: translateX(44px) scale(0.992);
}

.directory-search::after {
  position: absolute;
  inset: 1px 12px auto;
  height: 1px;
  border-radius: 999px;
  background: linear-gradient(90deg, transparent, rgb(255 255 255 / 96%), transparent);
  content: '';
  pointer-events: none;
}

.directory-segment {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  border: 1px solid rgb(203 213 225 / 82%);
  border-radius: 14px;
  padding: 3px;
  background: linear-gradient(180deg, rgb(226 232 240 / 82%), rgb(248 250 252 / 92%));
  box-shadow: inset 0 1px 2px rgb(15 23 42 / 8%), inset 0 1px 0 rgb(255 255 255 / 80%);
}

.directory-segment-indicator {
  position: absolute;
  inset: 3px auto 3px 3px;
  z-index: 0;
  width: calc((100% - 6px) / 4);
  border-radius: 11px;
  background: linear-gradient(135deg, rgb(15 118 110), rgb(13 148 136));
  box-shadow: 0 7px 14px -9px rgb(13 148 136 / 95%), inset 0 1px 0 rgb(255 255 255 / 30%);
  transition: transform 440ms var(--directory-spring);
}

.directory-scope-chip {
  border: 1px solid rgb(203 213 225 / 90%);
  background: linear-gradient(180deg, rgb(255 255 255 / 94%), rgb(241 245 249 / 90%));
  color: rgb(71 85 105);
  box-shadow: 0 6px 14px -12px rgb(15 23 42 / 80%), inset 0 1px 0 rgb(255 255 255 / 90%);
  transition: color 220ms ease, border-color 220ms ease, background 220ms ease, box-shadow 220ms ease, transform 300ms var(--directory-spring);
}

.directory-scope-chip:hover {
  border-color: rgb(94 234 212 / 82%);
  color: rgb(15 118 110);
}

.directory-scope-chip.is-active {
  border-color: rgb(45 212 191 / 80%);
  background: linear-gradient(145deg, rgb(204 251 241 / 88%), rgb(240 253 250 / 96%));
  color: rgb(17 94 89);
  box-shadow: 0 9px 18px -14px rgb(13 148 136 / 90%), inset 0 1px 0 rgb(255 255 255 / 88%);
}

.directory-scope-summary {
  height: 36px;
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 74%);
}

.directory-accordion-enter-active,
.directory-accordion-leave-active {
  transition: height 420ms var(--directory-spring), margin 420ms var(--directory-spring), opacity 220ms ease, transform 420ms var(--directory-spring);
}

.directory-accordion-enter-from,
.directory-accordion-leave-to {
  height: 0;
  margin-top: 0;
  opacity: 0;
  transform: translateY(-6px);
}

.directory-crossfade-enter-active,
.directory-crossfade-leave-active {
  transition: opacity 180ms ease, transform 260ms var(--directory-spring), filter 180ms ease;
}

.directory-crossfade-enter-from,
.directory-crossfade-leave-to {
  opacity: 0;
  filter: blur(2px);
  transform: translateY(3px) scale(0.96);
}

.directory-primary-action {
  background: linear-gradient(118deg, rgb(15 118 110), rgb(13 148 136) 58%, rgb(15 118 110));
  background-size: 200% 100%;
  box-shadow: 0 12px 22px -15px rgb(13 148 136 / 96%), inset 0 1px 0 rgb(255 255 255 / 30%);
  transition: background-position 480ms var(--directory-spring), box-shadow 260ms ease, transform 220ms var(--directory-spring);
}

.directory-primary-action::before {
  position: absolute;
  inset: 0;
  background: linear-gradient(110deg, transparent 28%, rgb(255 255 255 / 28%) 48%, transparent 68%);
  content: '';
  pointer-events: none;
  transform: translateX(-130%);
  transition: transform 620ms var(--directory-spring);
}

.directory-primary-action:hover {
  background-position: 100% 0;
  box-shadow: 0 16px 28px -17px rgb(13 148 136 / 100%), inset 0 1px 0 rgb(255 255 255 / 36%);
}

.directory-primary-action:hover::before {
  transform: translateX(130%);
}

.directory-ripple-control {
  isolation: isolate;
}

.directory-ripple-control > :not(.directory-ripple) {
  position: relative;
  z-index: 1;
}

.directory-ripple {
  position: absolute;
  z-index: 0;
  border-radius: 999px;
  background: rgb(255 255 255 / 42%);
  pointer-events: none;
  transform: translate(-50%, -50%) scale(0);
  animation: directory-ripple-expand 660ms ease-out forwards;
}

.directory-spin {
  animation: directory-spin 760ms linear infinite;
}

.directory-live-dot {
  animation: directory-live-pulse 1.8s ease-in-out infinite;
}

@keyframes directory-ripple-expand {
  65% { opacity: 0.34; }
  to { opacity: 0; transform: translate(-50%, -50%) scale(1); }
}

@keyframes directory-spin {
  to { transform: rotate(360deg); }
}

@keyframes directory-live-pulse {
  50% { box-shadow: 0 0 0 4px rgb(16 185 129 / 12%); opacity: 0.75; }
}

@media (prefers-reduced-motion: reduce) {
  .directory-backdrop,
  .directory-panel,
  .directory-segment-indicator,
  .directory-scope-chip,
  .directory-primary-action,
  .directory-primary-action::before,
  .directory-accordion-enter-active,
  .directory-accordion-leave-active,
  .directory-crossfade-enter-active,
  .directory-crossfade-leave-active {
    transition-duration: 0.01ms !important;
  }

  .directory-ripple,
  .directory-spin,
  .directory-live-dot {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
</style>

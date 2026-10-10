<script setup lang="ts">
import { Users } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import UserAvatar from '@/components/common/UserAvatar.vue'
import MemberDirectoryDrawer from '@/components/directory/MemberDirectoryDrawer.vue'
import type { DirectorySummary } from '@/api/directory'
import { directoryApi } from '@/api/directory'

withDefaults(defineProps<{
  currentFactoryId?: string
  currentDepartment?: string
}>(), {
  currentFactoryId: '',
  currentDepartment: '',
})

const SUMMARY_POLL_INTERVAL_MS = 60_000
const summary = ref<DirectorySummary | null>(null)
const drawerOpen = ref(false)
const failed = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null
let inFlight = false
let disposed = false, controller = new AbortController(), generation = 0
const auth = useAuthStore()
const eligible = computed(() => {
  const user = auth.currentUser; if (!user || user.identity?.employment_status === 'left') return false
  const formal = user.identity?.active_assignments_summary.some(a => a.org_unit_id !== 'group')
  if (formal) return true
  if (user.permissions.length && user.permissions.every(p => p.startsWith('carton_supplier:'))) return false
  return user.identity?.identity_mode !== 'v2' || !!user.permissions.length
})
const owner = computed(() => `${auth.currentUser?.id ?? ''}:${auth.currentUser?.identity?.employment_epoch ?? 0}:${auth.currentUser?.identity?.effective_context_key ?? ''}`)
watch(owner, () => { generation++; controller.abort(); controller = new AbortController(); inFlight = false; summary.value = null; drawerOpen.value = false; resume() })

const onlineCount = computed(() => summary.value?.state_counts.online ?? null)
const totalCount = computed(() => summary.value?.total_members ?? null)
const compactCount = computed(() => onlineCount.value === null ? '·' : String(onlineCount.value))
const summaryLabel = computed(() => {
  if (onlineCount.value === null || totalCount.value === null) return '查看组织成员'
  return `${onlineCount.value} 位在线`
})
const accessibleLabel = computed(() => {
  if (onlineCount.value === null || totalCount.value === null) return '打开组织成员目录'
  return `打开组织成员目录，${onlineCount.value} 人在线，共 ${totalCount.value} 人`
})

function canPoll() {
  return !disposed && eligible.value && document.visibilityState === 'visible' && navigator.onLine !== false
}

function clearTimer() {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
}

function schedule() {
  clearTimer()
  if (canPoll()) timer = setTimeout(() => void loadSummary(), SUMMARY_POLL_INTERVAL_MS)
}

async function loadSummary() {
  if (inFlight || !canPoll()) return
  inFlight = true
  const version = generation
  try {
    const result = await directoryApi.getSummary(controller.signal)
    if (disposed || version !== generation) return
    summary.value = result
    failed.value = false
  } catch {
    if (!disposed && version === generation) failed.value = true
  } finally {
    if (!disposed && version === generation) { inFlight = false; schedule() }
  }
}

function resume() {
  clearTimer()
  if (canPoll()) void loadSummary()
}

function handleVisibility() {
  if (document.visibilityState === 'visible') resume()
  else clearTimer()
}

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibility)
  window.addEventListener('focus', resume)
  window.addEventListener('online', resume)
  window.addEventListener('offline', clearTimer)
  resume()
})

onBeforeUnmount(() => {
  disposed = true; generation++; controller.abort()
  clearTimer()
  document.removeEventListener('visibilitychange', handleVisibility)
  window.removeEventListener('focus', resume)
  window.removeEventListener('online', resume)
  window.removeEventListener('offline', clearTimer)
})
</script>

<template>
  <button
    v-if="eligible"
    type="button"
    class="group relative inline-flex size-10 items-center justify-center gap-2.5 rounded-xl border border-teal-200/90 bg-gradient-to-b from-teal-50 to-white text-left shadow-[0_5px_16px_-12px_rgba(13,148,136,0.9)] transition-[color,background-color,border-color,box-shadow,transform] duration-150 hover:-translate-y-px hover:border-teal-300 hover:bg-teal-50 hover:shadow-[0_8px_20px_-12px_rgba(13,148,136,0.95)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30 active:translate-y-0 lg:h-10 lg:w-auto lg:min-w-[112px] lg:justify-start lg:px-2.5 2xl:min-w-[142px] 2xl:px-3"
    :title="failed ? '成员在线数据暂不可用，点击仍可打开目录' : '打开组织成员目录'"
    :aria-label="accessibleLabel"
    aria-haspopup="dialog"
    @click="drawerOpen = true"
  >
    <span v-if="summary?.preview_members.length" class="hidden shrink-0 -space-x-2 2xl:flex" aria-hidden="true">
      <UserAvatar
        v-for="member in summary.preview_members.filter(m => m.presence_state === 'online').slice(0, 3)"
        :key="member.id"
        :src="member.avatar_url"
        :name="member.display_name"
        size="sm"
        class="ring-2 ring-white transition-transform group-hover:-translate-y-0.5"
      />
    </span>
    <span class="relative grid size-7 shrink-0 place-items-center rounded-lg bg-teal-100/80 text-teal-800 ring-1 ring-inset ring-teal-200/70 2xl:hidden" aria-hidden="true">
      <Users class="size-4" stroke-width="2" />
      <span class="absolute -right-0.5 -top-0.5 size-2.5 rounded-full border-2 border-white bg-emerald-500" />
    </span>
    <span class="hidden min-w-0 lg:block">
      <span class="block whitespace-nowrap text-[11px] font-semibold leading-3.5 text-slate-600">成员目录</span>
      <span class="mt-0.5 block whitespace-nowrap text-xs font-bold leading-3.5 text-teal-800">
        {{ summaryLabel }}
      </span>
    </span>
    <span class="absolute -right-1.5 -top-1.5 grid min-h-4 min-w-4 place-items-center rounded-full border-2 border-white bg-teal-700 px-1 text-[9px] font-bold leading-3 text-white shadow-sm lg:hidden" aria-hidden="true">
      {{ compactCount }}
    </span>
  </button>

  <MemberDirectoryDrawer
    :open="drawerOpen"
    :current-factory-id="currentFactoryId"
    :current-department="currentDepartment"
    @close="drawerOpen = false"
  />
</template>

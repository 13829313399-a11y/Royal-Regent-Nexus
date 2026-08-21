<script setup lang="ts">
import { ChevronLeft, ChevronRight, Search, Users } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AvatarPreviewDialog from '@/components/directory/AvatarPreviewDialog.vue'
import MemberDirectoryList from '@/components/directory/MemberDirectoryList.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import type { DirectoryMember, DirectoryStateCounts, PresenceFilter } from '@/api/directory'
import { directoryApi } from '@/api/directory'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const PAGE_SIZE = 36
const SEARCH_DEBOUNCE_MS = 250

function queryString(name: string) {
  const value = route.query[name]
  return typeof value === 'string' ? value : ''
}

function queryPage() {
  const parsed = Number.parseInt(queryString('page'), 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1
}

function queryPresence(): PresenceFilter {
  const value = queryString('presence')
  return ['online', 'away', 'offline'].includes(value) ? value as PresenceFilter : 'all'
}

const searchText = ref(queryString('q'))
const queryText = ref(queryString('q'))
const presence = ref<PresenceFilter>(queryPresence())
const factoryFilter = ref(queryString('factory_id'))
const departmentFilter = ref(queryString('department'))
const page = ref(queryPage())
const members = ref<DirectoryMember[]>([])
const counts = ref<DirectoryStateCounts>({ online: 0, away: 0, offline: 0 })
const total = ref(0)
const totalPages = ref(0)
const loading = ref(false)
const error = ref('')
const stale = ref(false)
const previewMember = ref<DirectoryMember | null>(null)
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let requestSequence = 0

const currentFactoryId = computed(() => authStore.currentUser?.profile?.primary_factory_id ?? '')
const currentDepartment = computed(() => authStore.currentUser?.profile?.primary_department ?? '')
const allCount = computed(() => counts.value.online + counts.value.away + counts.value.offline)

function routeQuery() {
  const query: Record<string, string> = {}
  if (queryText.value) query.q = queryText.value
  if (presence.value !== 'all') query.presence = presence.value
  if (factoryFilter.value) query.factory_id = factoryFilter.value
  if (departmentFilter.value) query.department = departmentFilter.value
  if (page.value > 1) query.page = String(page.value)
  return query
}

async function syncAndLoad() {
  await router.replace({ name: 'people-directory', query: routeQuery() })
  await loadMembers()
}

async function loadMembers(background = false) {
  const sequence = ++requestSequence
  if (!background || !members.value.length) loading.value = true
  try {
    const result = await directoryApi.getMembers({
      page: page.value,
      page_size: PAGE_SIZE,
      q: queryText.value,
      presence: presence.value,
      factory_id: factoryFilter.value,
      department: departmentFilter.value,
    })
    if (sequence !== requestSequence) return
    members.value = result.items
    counts.value = result.state_counts
    total.value = result.total
    totalPages.value = result.total_pages
    error.value = ''
    stale.value = false
  } catch (caught) {
    if (sequence !== requestSequence) return
    error.value = getApiErrorMessage(caught)
    stale.value = members.value.length > 0
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  void syncAndLoad()
}

function setPresence(value: PresenceFilter) {
  presence.value = value
  applyFilters()
}

function setCurrentFactory() {
  factoryFilter.value = factoryFilter.value ? '' : currentFactoryId.value
  applyFilters()
}

function setCurrentDepartment() {
  departmentFilter.value = departmentFilter.value ? '' : currentDepartment.value
  applyFilters()
}

function goToPage(target: number) {
  if (target < 1 || target > totalPages.value || target === page.value) return
  page.value = target
  void syncAndLoad().then(() => window.scrollTo({ top: 0, behavior: 'smooth' }))
}

function handleSearchInput() {
  if (debounceTimer !== null) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    queryText.value = searchText.value.trim()
    applyFilters()
  }, SEARCH_DEBOUNCE_MS)
}

onMounted(() => {
  void loadMembers()
})

onBeforeUnmount(() => {
  requestSequence += 1
  if (debounceTimer !== null) clearTimeout(debounceTimer)
})
</script>

<template>
  <div class="app-page space-y-6">
    <PageHeader
      eyebrow="Organization Directory"
      title="成员目录"
      description="按姓名、职位、厂区、部门和近期连接状态查找企业中台成员。"
    />

    <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="成员状态概览">
      <button
        v-for="stat in ([
          { key: 'all', label: '全部成员', value: allCount, tone: 'slate' },
          { key: 'online', label: '在线', value: counts.online, tone: 'teal' },
          { key: 'away', label: '离开', value: counts.away, tone: 'amber' },
          { key: 'offline', label: '离线', value: counts.offline, tone: 'slate' },
        ] as const)"
        :key="stat.key"
        type="button"
        class="enterprise-panel interactive-surface rounded-xl px-4 py-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
        :aria-pressed="presence === stat.key"
        @click="setPresence(stat.key)"
      >
        <span class="text-xs font-semibold text-slate-500">{{ stat.label }}</span>
        <span class="mt-1 block text-2xl font-semibold text-slate-950">{{ stat.value }}</span>
      </button>
    </section>

    <SectionPanel title="组织成员" subtitle="目录仅展示在职且已启用的企业账号；每页最多显示 36 人。">
      <div class="grid gap-3 lg:grid-cols-[minmax(240px,1.4fr)_180px_180px]">
        <label class="relative block">
          <span class="sr-only">搜索成员</span>
          <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            v-model="searchText"
            type="search"
            maxlength="64"
            autocomplete="off"
            placeholder="搜索姓名、职位、厂区或部门"
            class="h-11 w-full rounded-xl border border-slate-300 bg-white pl-10 pr-3 text-sm"
            @input="handleSearchInput"
          >
        </label>
        <label>
          <span class="sr-only">厂区筛选</span>
          <input
            v-model.trim="factoryFilter"
            type="text"
            maxlength="64"
            placeholder="厂区"
            class="h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm"
            @change="applyFilters"
          >
        </label>
        <label>
          <span class="sr-only">部门筛选</span>
          <input
            v-model.trim="departmentFilter"
            type="text"
            maxlength="64"
            placeholder="部门"
            class="h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm"
            @change="applyFilters"
          >
        </label>
      </div>

      <div class="mt-3 flex flex-wrap gap-2" aria-label="快捷筛选">
        <button
          v-if="currentFactoryId"
          type="button"
          class="rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ring-inset"
          :class="factoryFilter === currentFactoryId ? 'bg-teal-50 text-teal-800 ring-teal-300' : 'bg-white text-slate-600 ring-slate-300'"
          :aria-pressed="factoryFilter === currentFactoryId"
          @click="setCurrentFactory"
        >
          当前厂区 · {{ currentFactoryId }}
        </button>
        <button
          v-if="currentDepartment"
          type="button"
          class="rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ring-inset"
          :class="departmentFilter === currentDepartment ? 'bg-teal-50 text-teal-800 ring-teal-300' : 'bg-white text-slate-600 ring-slate-300'"
          :aria-pressed="departmentFilter === currentDepartment"
          @click="setCurrentDepartment"
        >
          当前部门 · {{ currentDepartment }}
        </button>
      </div>

      <div class="mt-5">
        <MemberDirectoryList
          :members="members"
          :loading="loading"
          :error="error"
          :stale="stale"
          grid
          @retry="loadMembers()"
          @preview="previewMember = $event"
        />
      </div>

      <div v-if="totalPages > 1" class="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-5">
        <p class="text-sm text-slate-500">第 {{ page }} / {{ totalPages }} 页 · 共 {{ total }} 人</p>
        <div class="flex gap-2">
          <button
            type="button"
            class="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-45"
            :disabled="page <= 1 || loading"
            @click="goToPage(page - 1)"
          >
            <ChevronLeft class="size-4" aria-hidden="true" />
            上一页
          </button>
          <button
            type="button"
            class="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-45"
            :disabled="page >= totalPages || loading"
            @click="goToPage(page + 1)"
          >
            下一页
            <ChevronRight class="size-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div v-if="!loading && !members.length && !error" class="sr-only">
        <Users aria-hidden="true" />
      </div>

      <p class="mt-5 border-t border-slate-100 pt-4 text-center text-xs leading-5 text-slate-500">
        “在线/离开/离线”仅表示近期是否连接企业中台，不代表工作状态、岗位出勤或响应承诺。
      </p>
    </SectionPanel>

    <AvatarPreviewDialog :member="previewMember" @close="previewMember = null" />
  </div>
</template>

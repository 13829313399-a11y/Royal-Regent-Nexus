<script setup lang="ts">
import { computed, ref } from 'vue'
import { BriefcaseBusiness, Building2, Factory, LogOut } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { departmentMap, factoryContexts } from '@/data/enterpriseMock'

withDefaults(defineProps<{
  compact?: boolean
}>(), {
  compact: false,
})

const router = useRouter()
const authStore = useAuthStore()
const isLoggingOut = ref(false)

const displayName = computed(() =>
  authStore.currentUser?.display_name
  || authStore.currentUser?.username
  || '已登录账号',
)

const roleLabel = computed(() => authStore.roles[0] ?? '系统用户')
const userInitial = computed(() => displayName.value.trim().charAt(0) || '账')
const accountName = computed(() => authStore.currentUser?.username ?? '当前账号')

const internalDepartmentLabels: Record<string, string> = {
  system: '系统管理',
  management: '综合管理',
  molding: '啤机部',
  warehouse: '仓管部',
  'carton-warehouse': '纸箱仓管',
}

function formatScopeList(scopes: string[], fallback: string, formatter: (scope: string) => string) {
  const normalizedScopes = Array.from(
    new Set(scopes.map((scope) => scope.trim()).filter(Boolean)),
  )

  if (!normalizedScopes.length) {
    return fallback
  }

  if (normalizedScopes.includes('*')) {
    return formatter('*')
  }

  const labels = normalizedScopes.map(formatter)
  return labels.length > 3 ? `${labels.slice(0, 3).join('、')}等${labels.length}项` : labels.join('、')
}

const factoryLabel = computed(() => formatScopeList(
  authStore.factoryScopes,
  '未限定厂区',
  (scope) => {
    if (scope === '*') {
      return '全部厂区'
    }

    return factoryContexts.find((factory) => factory.id === scope)?.shortName ?? scope
  },
))

const departmentLabel = computed(() => formatScopeList(
  authStore.departmentScopes,
  '未限定部门',
  (scope) => {
    if (scope === '*') {
      return '全部部门'
    }

    return internalDepartmentLabels[scope]
      ?? departmentMap[scope as keyof typeof departmentMap]?.name
      ?? scope
  },
))

const positionLabel = computed(() => {
  if (!authStore.roles.length) {
    return '未配置职位'
  }

  return authStore.roles.length > 3
    ? `${authStore.roles.slice(0, 3).join('、')}等${authStore.roles.length}项`
    : authStore.roles.join('、')
})

async function handleLogout() {
  if (isLoggingOut.value) {
    return
  }

  isLoggingOut.value = true
  try {
    await authStore.logout()
  } catch {
    authStore.clearSession()
  } finally {
    await router.replace({ name: 'login', query: { logged_out: '1' } })
    isLoggingOut.value = false
  }
}
</script>

<template>
  <div
    class="group relative inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1 text-slate-700 transition hover:border-teal-200 hover:bg-teal-50/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
    tabindex="0"
    aria-label="账号详情"
  >
    <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-teal-100 text-[11px] font-bold text-teal-700">
      {{ userInitial }}
    </span>
    <span v-if="!compact" class="hidden min-w-0 leading-tight sm:block">
      <span class="block max-w-28 truncate text-[12px] font-semibold text-slate-800">{{ displayName }}</span>
      <span class="block max-w-28 truncate text-[10px] text-slate-400">{{ roleLabel }}</span>
    </span>
    <button
      type="button"
      class="inline-flex h-7 items-center justify-center gap-1 rounded-md border border-slate-200 px-2 text-[11px] font-semibold text-slate-500 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600 disabled:cursor-wait disabled:opacity-60"
      :disabled="isLoggingOut"
      aria-label="退出登录"
      title="退出登录"
      @click="handleLogout"
    >
      <LogOut class="size-3.5" aria-hidden="true" />
      <span class="hidden 2xl:inline">{{ isLoggingOut ? '退出中' : '退出' }}</span>
    </button>
    <div
      class="pointer-events-none absolute right-0 top-11 z-50 w-72 translate-y-1 rounded-xl border border-slate-200 bg-white p-3 text-left text-slate-700 opacity-0 shadow-xl shadow-slate-900/10 transition duration-150 group-hover:pointer-events-auto group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:translate-y-0 group-focus-within:opacity-100"
      role="status"
      aria-live="polite"
    >
      <span class="absolute -top-1.5 right-9 h-3 w-3 rotate-45 border-l border-t border-slate-200 bg-white" aria-hidden="true" />
      <div class="mb-3 flex items-center gap-2.5 border-b border-slate-100 pb-3">
        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-100 text-[12px] font-bold text-teal-700">
          {{ userInitial }}
        </span>
        <span class="min-w-0">
          <span class="block truncate text-sm font-bold text-slate-900">{{ displayName }}</span>
          <span class="block truncate text-[11px] text-slate-500">{{ accountName }}</span>
        </span>
      </div>
      <div class="space-y-2">
        <div class="flex items-start gap-2 rounded-lg bg-slate-50 px-2.5 py-2">
          <Factory class="mt-0.5 size-4 shrink-0 text-teal-600" aria-hidden="true" />
          <span class="min-w-0">
            <span class="block text-[11px] font-semibold text-slate-400">厂区</span>
            <span class="block break-words text-[12px] font-semibold text-slate-800">{{ factoryLabel }}</span>
          </span>
        </div>
        <div class="flex items-start gap-2 rounded-lg bg-slate-50 px-2.5 py-2">
          <Building2 class="mt-0.5 size-4 shrink-0 text-sky-600" aria-hidden="true" />
          <span class="min-w-0">
            <span class="block text-[11px] font-semibold text-slate-400">部门</span>
            <span class="block break-words text-[12px] font-semibold text-slate-800">{{ departmentLabel }}</span>
          </span>
        </div>
        <div class="flex items-start gap-2 rounded-lg bg-slate-50 px-2.5 py-2">
          <BriefcaseBusiness class="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden="true" />
          <span class="min-w-0">
            <span class="block text-[11px] font-semibold text-slate-400">职位</span>
            <span class="block break-words text-[12px] font-semibold text-slate-800">{{ positionLabel }}</span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

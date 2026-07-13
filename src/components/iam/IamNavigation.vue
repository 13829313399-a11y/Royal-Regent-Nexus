<script setup lang="ts">
import { BookOpenCheck, ClipboardCheck, FileClock, Home, ShieldCheck, UsersRound } from '@lucide/vue'
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

defineProps<{
  title: string
  subtitle?: string
}>()

const authStore = useAuthStore()
const items = computed(() => [
  { to: '/system/users', label: '用户与授权', icon: UsersRound, permissions: ['system:user_manage'] },
  { to: '/system/iam/roles', label: '角色模板', icon: ShieldCheck, permissions: ['system:permission_catalog_read'] },
  { to: '/system/iam/permissions', label: '权限目录', icon: BookOpenCheck, permissions: ['system:permission_catalog_read'] },
  { to: '/system/iam/requests', label: '权限申请', icon: ClipboardCheck, permissions: ['system:access_request', 'system:access_approve'] },
  { to: '/system/iam/audit', label: '操作记录', icon: FileClock, permissions: ['system:audit_read'] },
].filter((item) => item.permissions.some((permission) => authStore.can(permission))))
</script>

<template>
  <header class="border-b border-slate-200 bg-white">
    <div class="mx-auto flex max-w-[1480px] flex-col gap-4 px-5 py-5 xl:px-8">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="mb-1 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-emerald-700">
            <ShieldCheck class="size-4" aria-hidden="true" />
            Identity &amp; Access Management
          </div>
          <h1 class="text-2xl font-bold tracking-tight text-slate-950">{{ title }}</h1>
          <p v-if="subtitle" class="mt-1 text-sm text-slate-500">{{ subtitle }}</p>
        </div>
        <RouterLink class="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50" to="/">
          <Home class="size-4" aria-hidden="true" />返回首页
        </RouterLink>
      </div>

      <nav class="flex gap-1 overflow-x-auto" aria-label="权限管理导航">
        <RouterLink
          v-for="item in items"
          :key="item.to"
          :to="item.to"
          class="flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"
          active-class="bg-emerald-50 text-emerald-800"
        >
          <component :is="item.icon" class="size-4" aria-hidden="true" />
          {{ item.label }}
        </RouterLink>
      </nav>
    </div>
  </header>
</template>

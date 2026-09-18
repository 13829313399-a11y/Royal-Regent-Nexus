<script setup lang="ts">
import { Home, ShieldCheck, UsersRound } from '@lucide/vue'
import { computed } from 'vue'
import { shouldShowPageNavigation } from '@/config/pageAccessPolicy'
import { useAuthStore } from '@/stores/auth'

withDefaults(defineProps<{
  title: string
  subtitle?: string
  compact?: boolean
  /**
   * 外观变体。默认 `default` 保持原有样式；
   * `/system/iam/roles` 传入 `portal`，用户权限职位调整页保持默认。
   */
  appearance?: 'default' | 'portal'
}>(), {
  compact: false,
  appearance: 'default',
})

const authStore = useAuthStore()
const items = computed(() => [
  { to: '/system/users', label: '用户与授权', icon: UsersRound, permissions: ['system:user_manage'] },
  { to: '/system/iam/roles', label: '内置职位权限', icon: ShieldCheck, permissions: ['system:permission_catalog_read'] },
].filter((item) => shouldShowPageNavigation(
  item.permissions,
  (permission) => authStore.can(permission),
)))
</script>

<template>
  <header
    class="border-b border-slate-200 bg-white"
    :class="appearance === 'portal' ? 'rrn-portal-region' : ''"
    :data-portal-region="appearance === 'portal' ? 'roles-header' : undefined"
  >
    <div
      class="mx-auto flex max-w-[1600px] flex-col px-5 xl:px-6"
      :class="compact ? 'gap-1 py-2' : 'gap-4 py-5'"
    >
      <div class="flex flex-wrap items-start justify-between" :class="compact ? 'gap-3' : 'gap-4'">
        <div :class="compact ? 'flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3' : ''">
          <div class="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.17em] text-emerald-700" :class="compact ? 'mb-0' : 'mb-0.5'">
            <ShieldCheck class="size-3.5" aria-hidden="true" />
            Identity &amp; Access Management
          </div>
          <h1 class="font-bold tracking-tight text-slate-950" :class="compact ? 'text-[22px] leading-7' : 'text-2xl'">{{ title }}</h1>
          <p v-if="subtitle" class="text-slate-500" :class="compact ? 'w-full text-[13px] leading-5' : 'mt-0.5 text-sm'">{{ subtitle }}</p>
        </div>
        <RouterLink class="inline-flex h-9 items-center gap-2 rounded-[10px] border border-slate-200 px-3 text-[13px] font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50" to="/">
          <Home class="size-4" aria-hidden="true" />返回首页
        </RouterLink>
      </div>

      <nav class="flex gap-1 overflow-x-auto" aria-label="权限管理导航">
        <RouterLink
          v-for="item in items"
          :key="item.to"
          :to="item.to"
          class="flex h-9 shrink-0 items-center gap-2 rounded-[10px] px-3 text-[13px] font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"
          active-class="bg-emerald-50 text-emerald-800"
        >
          <component :is="item.icon" class="size-4" aria-hidden="true" />
          {{ item.label }}
        </RouterLink>
      </nav>
    </div>
  </header>
</template>

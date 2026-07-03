<script setup lang="ts">
import { computed } from 'vue'
import { Bell, Search } from '@lucide/vue'
import { useRoute } from 'vue-router'
import { factoryContexts } from '@/data/enterpriseMock'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import RouteLoadingBar from '@/components/layout/RouteLoadingBar.vue'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const appStore = useAppStore()

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
</script>

<template>
  <header class="sticky top-0 z-30 h-auto border-b border-slate-200 bg-white/95 backdrop-blur">
    <div class="flex min-h-[72px] items-center gap-5 px-6">
      <RouterLink to="/" class="flex min-w-[236px] items-center gap-3">
        <span class="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-lg">
          <img
            src="/brand/huadeng_group_dynamic_logo.svg"
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

      <button
        type="button"
        class="flex size-9 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-500 hover:text-slate-950"
        aria-label="Notifications"
      >
        <Bell class="size-4" aria-hidden="true" />
      </button>

      <AccountMenu />
    </div>
    <RouteLoadingBar />
  </header>
</template>

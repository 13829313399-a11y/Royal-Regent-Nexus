<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Menu, Search } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { factoryContexts, type FactoryContextId } from '@/data/enterpriseMock'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import MemberDirectoryEntry from '@/components/directory/MemberDirectoryEntry.vue'
import NotificationCenter from '@/components/notifications/NotificationCenter.vue'
import RouteLoadingBar from '@/components/layout/RouteLoadingBar.vue'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const props = withDefaults(defineProps<{
  navigationOpen?: boolean
}>(), {
  navigationOpen: false,
})
const emit = defineEmits<{
  toggleNavigation: []
}>()
const brandLogoSrc = '/brand/huadeng_group_dynamic_logo_topbar.svg'
const navigationTriggerRef = ref<HTMLButtonElement | null>(null)

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

function selectFactory(factoryId: FactoryContextId) {
  appStore.setActiveFactory(factoryId)

  if (!route.path.startsWith('/modules') && route.query.factory === undefined) {
    return
  }

  void router.replace({
    path: route.path,
    query: {
      ...(route.query ?? {}),
      factory: factoryId,
    },
    hash: route.hash,
  })
}

watch(() => props.navigationOpen, (isOpen, wasOpen) => {
  if (wasOpen && !isOpen) {
    void nextTick(() => navigationTriggerRef.value?.focus())
  }
})
</script>

<template>
  <header class="sticky top-0 z-40 h-auto border-b border-slate-200/80 bg-white/90 shadow-[0_1px_2px_rgba(15,23,42,0.04)] backdrop-blur-xl">
    <div class="flex min-h-16 items-center gap-2.5 px-3 sm:min-h-[72px] sm:gap-3 sm:px-4 2xl:gap-5 2xl:px-6">
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

      <RouterLink to="/" class="flex min-w-0 items-center gap-2.5 sm:min-w-[184px] 2xl:min-w-[236px] 2xl:gap-3">
        <span class="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-lg sm:size-14 2xl:size-16">
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

      <div class="hidden h-9 min-w-[180px] max-w-xl flex-1 items-center gap-2 rounded-lg border border-slate-200/90 bg-slate-50/75 px-3 shadow-[inset_0_1px_2px_rgba(15,23,42,0.03)] transition-colors hover:border-slate-300 hover:bg-white lg:flex xl:min-w-[220px]">
        <Search class="size-4 shrink-0 text-slate-400" aria-hidden="true" />
        <span class="truncate text-sm text-slate-500">{{ searchPlaceholder }}</span>
      </div>

      <div data-testid="topbar-member-directory-slot" class="ml-auto shrink-0 lg:ml-0">
        <MemberDirectoryEntry
          :current-factory-id="appStore.activeProductionFactory.id"
          :current-department="appStore.activeDepartmentId"
        />
      </div>

      <div data-testid="topbar-factory-switcher" class="hidden min-w-0 max-w-[40vw] items-center overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden xl:flex">
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
            :aria-pressed="factory.id === appStore.activeFactoryId"
            :title="factory.name"
            @click="selectFactory(factory.id)"
          >
            {{ getTopBarFactoryLabel(factory) }}
          </button>
        </div>
      </div>

      <NotificationCenter />
      <AccountMenu />
    </div>
    <RouteLoadingBar />
  </header>
</template>

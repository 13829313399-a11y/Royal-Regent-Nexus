<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { X } from '@lucide/vue'
import { RouterLink, useRoute } from 'vue-router'
import { shouldShowPageNavigation } from '@/config/pageAccessPolicy'
import { isModuleDepartmentId, navigationGroups, type NavigationItem } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()

const props = withDefaults(defineProps<{
  mobileOpen?: boolean
}>(), {
  mobileOpen: false,
})

const emit = defineEmits<{
  close: []
}>()
const sidebarRef = ref<HTMLElement | null>(null)
const mobileCloseButtonRef = ref<HTMLButtonElement | null>(null)

const visibleNavigationGroups = computed(() => navigationGroups
  .map((group) => ({
    ...group,
    items: group.items.filter((item) => shouldShowPageNavigation(
      item.permissions,
      (permission) => authStore.can(permission),
    )),
  }))
  .filter((group) => group.items.length))

function isActive(item: NavigationItem) {
  if (route.path === item.to) {
    return true
  }

  if (item.departmentId && route.path.startsWith('/modules')) {
    return item.departmentId === appStore.activeDepartmentId
  }

  return false
}

function handleSelect(item: NavigationItem) {
  if (item.departmentId && isModuleDepartmentId(item.departmentId)) {
    appStore.setActiveDepartment(item.departmentId)
  }

  emit('close')
}

function getMobileFocusableElements() {
  if (!sidebarRef.value) {
    return []
  }

  return Array.from(sidebarRef.value.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => element.getClientRects().length > 0)
}

function trapMobileFocus(event: KeyboardEvent) {
  if (!props.mobileOpen || event.key !== 'Tab') {
    return
  }

  const focusableElements = getMobileFocusableElements()
  const firstElement = focusableElements[0]
  const lastElement = focusableElements[focusableElements.length - 1]
  if (!firstElement || !lastElement) {
    return
  }

  if (event.shiftKey && document.activeElement === firstElement) {
    event.preventDefault()
    lastElement.focus()
  }
  else if (!event.shiftKey && document.activeElement === lastElement) {
    event.preventDefault()
    firstElement.focus()
  }
}

watch(() => props.mobileOpen, (isOpen) => {
  if (isOpen) {
    void nextTick(() => mobileCloseButtonRef.value?.focus())
  }
})
</script>

<template>
  <Transition name="nav-backdrop">
    <button
      v-if="mobileOpen"
      type="button"
      class="fixed inset-0 z-40 bg-slate-950/35 backdrop-blur-[2px] lg:hidden"
      aria-label="关闭全局导航"
      @click="emit('close')"
    />
  </Transition>

  <aside
    ref="sidebarRef"
    id="global-navigation"
    class="sidebar-scrollbar fixed inset-y-0 left-0 z-50 flex h-dvh w-[calc(100vw-2rem)] max-w-[300px] shrink-0 flex-col overflow-y-auto border-r border-slate-200/80 bg-white/98 shadow-2xl shadow-slate-950/15 transition-transform duration-200 ease-out lg:sticky lg:top-[75px] lg:z-20 lg:h-[calc(100vh-75px)] lg:w-[260px] lg:max-w-none lg:self-start lg:translate-x-0 lg:shadow-none"
    :class="mobileOpen ? 'visible translate-x-0' : 'invisible -translate-x-full lg:visible'"
    aria-label="全局导航"
    @keydown="trapMobileFocus"
    @keydown.esc="emit('close')"
  >
    <div class="flex items-center justify-between border-b border-slate-100 px-5 py-4 lg:hidden">
      <div>
        <p class="text-sm font-semibold text-slate-950">系统导航</p>
        <p class="mt-0.5 text-xs text-slate-500">{{ appStore.activeFactory.shortName }} · {{ appStore.activeDepartment.name }}</p>
      </div>
      <button
        ref="mobileCloseButtonRef"
        type="button"
        class="flex size-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-700"
        aria-label="关闭全局导航"
        @click="emit('close')"
      >
        <X class="size-4" aria-hidden="true" />
      </button>
    </div>

    <div class="flex-1 space-y-7 px-4 py-5 lg:py-7">
      <div v-for="group in visibleNavigationGroups" :key="group.label" class="space-y-2">
        <p class="px-2 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">
          {{ group.label }}
        </p>
        <nav class="space-y-1">
          <RouterLink
            v-for="item in group.items"
            :key="`${group.label}-${item.label}`"
            :to="item.to"
            class="group relative flex h-10 items-center gap-3 overflow-hidden rounded-lg px-3 text-sm transition-[color,background-color,box-shadow] duration-150"
            :class="isActive(item)
              ? 'bg-gradient-to-r from-teal-50 to-teal-50/45 font-semibold text-teal-800 shadow-[inset_0_0_0_1px_rgba(13,148,136,0.08)]'
              : 'text-slate-600 hover:bg-slate-50/90 hover:text-slate-950'"
            @click="handleSelect(item)"
          >
            <span
              v-if="isActive(item)"
              class="absolute inset-y-2 left-0 w-0.5 rounded-r-full bg-teal-600"
              aria-hidden="true"
            />
            <span
              class="flex size-7 shrink-0 items-center justify-center rounded-md transition-colors"
              :class="isActive(item) ? 'bg-white/85 text-teal-700 shadow-sm' : 'text-slate-400 group-hover:bg-white group-hover:text-slate-700'"
            >
              <component :is="item.icon" class="size-4" aria-hidden="true" />
            </span>
            <span class="truncate">{{ item.label }}</span>
          </RouterLink>
        </nav>
      </div>
    </div>

    <div class="p-4">
      <div class="surface-subtle rounded-xl p-4">
        <div class="mb-2 flex items-center justify-between">
          <p class="font-semibold text-slate-950">系统健康</p>
          <span class="inline-flex items-center gap-1.5 text-xs font-semibold text-teal-700">
            <span class="size-1.5 rounded-full bg-teal-500 shadow-[0_0_0_3px_rgba(20,184,166,0.12)]" aria-hidden="true" />
            在线
          </span>
        </div>
        <p class="text-sm text-slate-600">在线服务 23 / 24</p>
        <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200/80">
          <div class="h-full w-[88%] rounded-full bg-gradient-to-r from-teal-700 to-teal-500" />
        </div>
      </div>
    </div>
  </aside>
</template>

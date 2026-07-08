<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { isModuleDepartmentId, navigationGroups, type NavigationItem } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()

const visibleNavigationGroups = computed(() => navigationGroups
  .map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.permissions?.length || authStore.hasAnyPermission(item.permissions)),
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
}
</script>

<template>
  <aside class="sidebar-scrollbar hidden h-[calc(100vh-78px)] w-[260px] shrink-0 self-start overflow-y-auto border-r border-slate-200 bg-white lg:sticky lg:top-[78px] lg:flex lg:flex-col">
    <div class="flex-1 space-y-7 px-4 py-7">
      <div v-for="group in visibleNavigationGroups" :key="group.label" class="space-y-2">
        <p class="px-2 text-[11px] font-medium uppercase tracking-wide text-slate-500">
          {{ group.label }}
        </p>
        <nav class="space-y-1">
          <RouterLink
            v-for="item in group.items"
            :key="`${group.label}-${item.label}`"
            :to="item.to"
            class="flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors"
            :class="isActive(item)
              ? 'bg-teal-50 font-semibold text-teal-800'
              : 'text-slate-700 hover:bg-slate-50 hover:text-slate-950'"
            @click="handleSelect(item)"
          >
            <component :is="item.icon" class="size-4 shrink-0" aria-hidden="true" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </nav>
      </div>
    </div>

    <div class="p-4">
      <div class="rounded-lg border border-slate-200 bg-slate-50 p-4">
        <div class="mb-2 flex items-center justify-between">
          <p class="font-semibold text-slate-950">系统健康</p>
          <span class="text-xs text-teal-700">在线</span>
        </div>
        <p class="text-sm text-slate-600">在线服务 23 / 24</p>
        <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200">
          <div class="h-full w-[88%] rounded-full bg-teal-700" />
        </div>
      </div>
    </div>
  </aside>
</template>

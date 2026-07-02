<script setup lang="ts">
import { ArrowUpRight, Plus } from '@lucide/vue'
import { computed, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  departmentMap,
  departmentModuleRegistry,
  isModuleDepartmentId,
  type ModuleDepartmentId,
} from '@/data/enterpriseMock'
import { getMoldingSampleModuleStats } from '@/data/moldingSampleWorkflowMock'
import DepartmentTabs from '@/components/modules/DepartmentTabs.vue'
import ModuleCard from '@/components/modules/ModuleCard.vue'
import PermissionMatrix from '@/components/modules/PermissionMatrix.vue'
import TodoQueue from '@/components/modules/TodoQueue.vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const appStore = useAppStore()

const currentDepartmentId = computed<ModuleDepartmentId>(() => {
  const department = String(route.params.department ?? '')
  return isModuleDepartmentId(department) ? department : 'engineering'
})

const departmentEntry = computed(() => departmentModuleRegistry[currentDepartmentId.value])
const currentDepartment = computed(() => departmentMap[currentDepartmentId.value])
const title = computed(() => `${appStore.activeProductionFactory.name} · ${currentDepartment.value.name}模块中心`)

const visibleModules = computed(() => {
  return departmentEntry.value.modules.map((module) => {
    if (currentDepartmentId.value === 'engineering' && module.id === 'molding-sample') {
      return {
        ...module,
        owner: `${appStore.activeProductionFactory.shortName} · 工程部公共模块`,
        stats: getMoldingSampleModuleStats(appStore.activeProductionFactory.id),
        route: `/modules/molding-sample?factory=${appStore.activeProductionFactory.id}`,
      }
    }

    if (currentDepartmentId.value === 'production' && module.id === 'injection-scheduling') {
      const route = `/modules/production/injection-scheduling?factory=${appStore.activeProductionFactory.id}`

      return {
        ...module,
        href: route,
        route,
      }
    }

    return module
  })
})

const featuredModule = computed(() => visibleModules.value[0])
const isExternalLink = (href: string) => /^https?:\/\//i.test(href)

watch(currentDepartmentId, (departmentId) => {
  appStore.setActiveDepartment(departmentId)
}, { immediate: true })
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
      <div>
        <h1 class="text-3xl font-semibold tracking-tight text-slate-950">{{ title }}</h1>
        <p class="mt-2 text-sm text-slate-600">
          {{ departmentEntry.heroSubtitle }}
        </p>
      </div>
      <button type="button" class="inline-flex h-10 items-center gap-2 rounded-lg bg-slate-950 px-6 text-sm font-semibold text-white">
        <Plus class="size-4" aria-hidden="true" />
        新增系统模块
      </button>
    </div>

    <DepartmentTabs />

    <div class="grid gap-6 xl:grid-cols-[1fr_380px]">
      <SectionPanel
        :title="departmentEntry.panelTitle"
        :subtitle="departmentEntry.panelSubtitle"
      >
        <div class="grid gap-5 md:grid-cols-2">
          <ModuleCard
            v-for="module in visibleModules"
            :key="module.id"
            :module="module"
            :active="featuredModule.id === module.id"
          />
        </div>

        <div class="mt-7 rounded-lg border border-slate-200 bg-white p-5">
          <h3 class="font-semibold text-slate-950">推荐下一批模块</h3>
          <p class="mt-3 text-sm text-slate-700">
            {{ departmentEntry.quickCandidates.join('、') }}
          </p>
          <div class="mt-5">
            <ProgressMeter :value="58" :tone="currentDepartmentId === 'production' ? 'amber' : 'teal'" />
          </div>
          <p class="mt-4 text-xs text-slate-500">
            {{ currentDepartment.focus }}
          </p>
        </div>
      </SectionPanel>

      <aside class="space-y-6">
        <SectionPanel title="模块聚焦" subtitle="这里先展示当前部门最优先建设的模块，点击卡片可进入独立详情页">
          <div class="space-y-5">
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="text-lg font-semibold text-slate-950">{{ featuredModule.title }}</h3>
                <p class="mt-1 text-sm text-slate-500">{{ featuredModule.owner }}</p>
              </div>
              <StatusPill :label="featuredModule.status" :tone="featuredModule.statusTone" />
            </div>

            <p class="text-sm leading-6 text-slate-700">{{ featuredModule.summary }}</p>

            <div class="grid gap-3 sm:grid-cols-3">
              <div
                v-for="metric in featuredModule.statusMetrics"
                :key="`${featuredModule.id}-${metric.label}`"
                class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
              >
                <p class="text-[11px] uppercase tracking-wide text-slate-500">{{ metric.label }}</p>
                <p class="mt-1 text-sm font-semibold text-slate-900">{{ metric.value }}</p>
              </div>
            </div>

            <div>
              <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">结构建议</p>
              <div class="mt-3 flex flex-wrap gap-2">
                <span
                  v-for="child in featuredModule.children"
                  :key="`${featuredModule.id}-${child.label}`"
                  class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600"
                >
                  {{ child.label }}
                </span>
              </div>
            </div>

            <div>
              <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">当前待办</p>
              <ul class="mt-3 space-y-2 text-sm text-slate-700">
                <li v-for="todo in featuredModule.todos" :key="todo" class="rounded-lg bg-slate-50 px-3 py-2">
                  {{ todo }}
                </li>
              </ul>
            </div>

            <div class="flex flex-wrap gap-3">
              <RouterLink
                v-if="featuredModule.href && !isExternalLink(featuredModule.href)"
                :to="featuredModule.href"
                class="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white"
              >
                打开系统
                <ArrowUpRight class="size-4" aria-hidden="true" />
              </RouterLink>
              <a
                v-else-if="featuredModule.href"
                :href="featuredModule.href"
                target="_blank"
                rel="noreferrer"
                class="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white"
              >
                打开系统
                <ArrowUpRight class="size-4" aria-hidden="true" />
              </a>
            </div>
          </div>
        </SectionPanel>

        <PermissionMatrix :rows="departmentEntry.permissionRows" />
        <TodoQueue :items="departmentEntry.todos" />
      </aside>
    </div>
  </div>
</template>

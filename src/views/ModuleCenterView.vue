<script setup lang="ts">
import { ArrowUpRight, Plus } from '@lucide/vue'
import { computed, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  departmentMap,
  departmentModuleRegistry,
  getFactoryScopedModule,
  getFactoryScopedRoute,
  getFactoryScopedTodoItems,
  isModuleDepartmentId,
  type ModuleDepartmentId,
} from '@/data/enterpriseMock'
import DepartmentTabs from '@/components/modules/DepartmentTabs.vue'
import ModuleCard from '@/components/modules/ModuleCard.vue'
import PermissionMatrix from '@/components/modules/PermissionMatrix.vue'
import TodoQueue from '@/components/modules/TodoQueue.vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()

const currentDepartmentId = computed<ModuleDepartmentId>(() => {
  const department = String(route.params.department ?? '')
  return isModuleDepartmentId(department) ? department : 'engineering'
})

const departmentEntry = computed(() => departmentModuleRegistry[currentDepartmentId.value])
const currentDepartment = computed(() => departmentMap[currentDepartmentId.value])
const title = computed(() => `${appStore.activeProductionFactory.name} · ${currentDepartment.value.name}模块中心`)
const visibleDepartmentTodos = computed(() => getFactoryScopedTodoItems(
  departmentEntry.value.todos,
  appStore.activeProductionFactory.id,
))

const visibleModules = computed(() => {
  const factory = appStore.activeProductionFactory

  return departmentEntry.value.modules
    .filter((module) => {
      if (module.factoryIds?.length && !module.factoryIds.includes(factory.id)) return false
      if (
        module.strictAccess
        && module.permissions?.length
        && !authStore.canAny(module.permissions, factory.id, 'three-d-printing')
      ) return false
      return true
    })
    .map((module) => {
    const scopedModule = getFactoryScopedModule(module, factory.id)

    if (currentDepartmentId.value === 'engineering' && module.id === 'molding-sample') {
      return {
        ...scopedModule,
        owner: `${factory.shortName} · 工程部公共模块`,
        stats: '工程开单后流转到生产任务',
        route: getFactoryScopedRoute('/modules/molding-sample', factory.id),
        statusMetrics: [
          { label: '开单', value: '工程登记', tone: 'teal' as const },
          { label: '流转', value: '主管审核', tone: 'blue' as const },
          { label: '闭环', value: '生产回传', tone: 'green' as const },
        ],
      }
    }

    if (currentDepartmentId.value === 'production' && module.id === 'molding-sample-production-task') {
      const route = getFactoryScopedRoute('/modules/production/molding-sample-tasks', factory.id)

      return {
        ...scopedModule,
        owner: `${factory.shortName} · 啤机部任务单`,
        stats: '主管审核后进入任务队列',
        route,
        statusMetrics: [
          { label: '接收', value: '审核通知', tone: 'teal' as const },
          { label: '执行', value: '用料回填', tone: 'amber' as const },
          { label: '回传', value: '工程同步', tone: 'green' as const },
        ],
      }
    }

    return scopedModule
    })
})

const featuredModule = computed(() => visibleModules.value[0] ?? null)
const isExternalLink = (href: string) => /^https?:\/\//i.test(href)

watch(currentDepartmentId, (departmentId) => {
  appStore.setActiveDepartment(departmentId)
}, { immediate: true })
</script>

<template>
  <div class="app-page space-y-6">
    <PageHeader
      eyebrow="Department Workspace"
      :title="title"
      :description="departmentEntry.heroSubtitle"
    >
      <template #actions>
        <Button type="button" size="lg">
          <Plus class="size-4" aria-hidden="true" />
          新增系统模块
        </Button>
      </template>
    </PageHeader>

    <DepartmentTabs />

    <div class="grid gap-6 xl:grid-cols-[1fr_380px]">
      <SectionPanel
        :title="departmentEntry.panelTitle"
        :subtitle="departmentEntry.panelSubtitle"
      >
        <div class="reveal-grid grid gap-5 md:grid-cols-2">
          <ModuleCard
            v-for="module in visibleModules"
            :key="module.id"
            :module="module"
            :active="featuredModule?.id === module.id"
          />
        </div>

        <div class="surface-subtle mt-7 rounded-xl p-5">
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
          <div v-if="featuredModule" class="space-y-5">
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
                class="surface-subtle rounded-lg px-3 py-2"
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
                class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
              >
                打开系统
                <ArrowUpRight class="size-4" aria-hidden="true" />
              </RouterLink>
              <a
                v-else-if="featuredModule.href"
                :href="featuredModule.href"
                target="_blank"
                rel="noreferrer"
                class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
              >
                打开系统
                <ArrowUpRight class="size-4" aria-hidden="true" />
              </a>
            </div>
          </div>
          <p v-else class="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center text-sm text-slate-500">
            当前厂区没有可显示的模块。
          </p>
        </SectionPanel>

        <PermissionMatrix :rows="departmentEntry.permissionRows" />
        <TodoQueue :items="visibleDepartmentTodos" />
      </aside>
    </div>
  </div>
</template>

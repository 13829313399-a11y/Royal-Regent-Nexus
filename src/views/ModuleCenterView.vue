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
import PortalHero from '@/components/portal/PortalHero.vue'
import { getDepartmentPresentation } from '@/components/portal/portalPresentation'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { SPRAY_BASE, isSprayFactory, sprayEnabled } from '@/features/spray-production/contracts'

const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()

const currentDepartmentId = computed<ModuleDepartmentId>(() => {
  const department = String(route.params.department ?? '')
  return isModuleDepartmentId(department) ? department : 'engineering'
})

const departmentEntry = computed(() => departmentModuleRegistry[currentDepartmentId.value])
const currentDepartment = computed(() => departmentMap[currentDepartmentId.value])
/**
 * 部门展示配置由当前部门参数计算，不只在 onMounted 读取一次：
 * 同一组件实例会在部门参数变化时复用。
 */
const departmentPresentation = computed(() => getDepartmentPresentation(currentDepartmentId.value))
const portalRootStyle = computed(() => ({
  '--portal-accent': departmentPresentation.value.accent,
  '--portal-accent-soft': departmentPresentation.value.accentSoft,
}))
const title = computed(() => `${appStore.activeProductionFactory.name} · ${currentDepartment.value.name}模块中心`)
const visibleDepartmentTodos = computed(() => getFactoryScopedTodoItems(
  departmentEntry.value.todos,
  appStore.activeProductionFactory.id,
))

const visibleModules = computed(() => {
  const factory = appStore.activeProductionFactory

  return departmentEntry.value.modules
    .filter((module) => {
      // 占位卡仅属于华康A，不随集团的生产厂区兜底显示。
      if (module.id === 'uv-printing' && appStore.activeFactoryId !== 'huakang-a') return false
      if (module.id === 'spray-production' && !isSprayFactory(appStore.activeFactoryId)) return false
      if (module.factoryIds?.length && !module.factoryIds.includes(factory.id)) return false
      if (
        module.strictAccess
        && module.permissions?.length
        && !authStore.canAny(module.permissions, factory.id, module.permissionDepartment)
      ) return false
      return true
    })
    .map((module) => {
    const scopedModule = getFactoryScopedModule(module, factory.id)

    if (module.id === 'spray-production' && sprayEnabled()) {
      const authorized = authStore.can('spray_ops:read', factory.id, 'production')
      return { ...scopedModule, summary: '分批来料、工序排产、实绩质量、用料与交收月结',
        status: authorized ? '工作区' : '权限待开通', statusTone: 'teal' as const,
        stats: authorized ? '进入当前工厂工作区' : '需要当前工厂授权',
        detailPage: authorized, route: authorized ? getFactoryScopedRoute(`${SPRAY_BASE}/overview`, factory.id) : undefined }
    }

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
  <div
    class="rrn-portal app-page space-y-6"
    data-portal-ui="jade-v3"
    :style="portalRootStyle"
  >
    <PortalHero
      eyebrow="Department Workspace"
      :title="title"
      :description="departmentEntry.heroSubtitle"
      :motif="departmentPresentation.motif"
      pending-note="新增系统模块暂未接入"
    >
      <template #actions>
        <Button type="button" size="lg" disabled>
          <Plus class="size-4" aria-hidden="true" />
          新增系统模块
        </Button>
      </template>
    </PortalHero>

    <DepartmentTabs />

    <div class="grid gap-6 xl:grid-cols-[1fr_380px]">
      <SectionPanel
        class="portal-section"
        :title="departmentEntry.panelTitle"
        :subtitle="departmentEntry.panelSubtitle"
      >
        <div class="portal-module-grid grid gap-5 md:grid-cols-2">
          <ModuleCard
            v-for="(module, index) in visibleModules"
            :key="module.id"
            :module="module"
            :index="index"
            :active="featuredModule?.id === module.id"
          />
        </div>

        <div class="portal-candidates">
          <h3 class="portal-candidates__title">推荐下一批模块</h3>
          <p class="portal-candidates__list">
            {{ departmentEntry.quickCandidates.join('、') }}
          </p>
          <div class="portal-candidates__meter">
            <ProgressMeter :value="58" :tone="currentDepartmentId === 'production' ? 'amber' : 'teal'" />
          </div>
          <p class="portal-candidates__note">
            规划示意，不代表已完成比例 · {{ currentDepartment.focus }}
          </p>
        </div>
      </SectionPanel>

      <aside class="space-y-6">
        <SectionPanel
          class="portal-section"
          title="模块聚焦"
          subtitle="这里先展示当前部门最优先建设的模块，点击卡片可进入独立详情页"
        >
          <div v-if="featuredModule" class="space-y-5">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <h3 class="portal-focus__title">{{ featuredModule.title }}</h3>
                <p class="portal-focus__owner">{{ featuredModule.owner }}</p>
              </div>
              <StatusPill :label="featuredModule.status" :tone="featuredModule.statusTone" />
            </div>

            <p class="portal-focus__summary">{{ featuredModule.summary }}</p>

            <div v-if="featuredModule.statusMetrics.length" class="portal-focus__metrics grid gap-3 sm:grid-cols-3">
              <div
                v-for="metric in featuredModule.statusMetrics"
                :key="`${featuredModule.id}-${metric.label}`"
                class="portal-focus__metric"
              >
                <p class="portal-focus__metric-label">{{ metric.label }}</p>
                <p class="portal-focus__metric-value">{{ metric.value }}</p>
              </div>
            </div>

            <div v-if="featuredModule.children.length">
              <p class="portal-focus__label">结构建议</p>
              <div class="mt-3 flex flex-wrap gap-2">
                <span
                  v-for="child in featuredModule.children"
                  :key="`${featuredModule.id}-${child.label}`"
                  class="portal-module-card__child"
                >
                  {{ child.label }}
                </span>
              </div>
            </div>

            <div v-if="featuredModule.todos.length">
              <p class="portal-focus__label">当前待办</p>
              <ul class="portal-focus__todos mt-3">
                <li v-for="todo in featuredModule.todos" :key="todo" class="portal-focus__todo">
                  {{ todo }}
                </li>
              </ul>
            </div>

            <div v-if="featuredModule.href" class="flex flex-wrap gap-3">
              <RouterLink
                v-if="!isExternalLink(featuredModule.href)"
                :to="featuredModule.href"
                class="portal-action portal-action--primary"
              >
                打开系统
                <ArrowUpRight class="portal-action__arrow size-4" aria-hidden="true" />
              </RouterLink>
              <a
                v-else
                :href="featuredModule.href"
                target="_blank"
                rel="noreferrer"
                class="portal-action portal-action--primary"
              >
                打开系统
                <ArrowUpRight class="portal-action__arrow size-4" aria-hidden="true" />
              </a>
            </div>
          </div>
          <p v-else class="portal-focus__empty">
            当前厂区没有可显示的模块。
          </p>
        </SectionPanel>

        <PermissionMatrix
          appearance="portal"
          :rows="departmentEntry.permissionRows"
          :note="departmentPresentation.permissionNote"
        />
        <TodoQueue
          appearance="portal"
          :items="visibleDepartmentTodos"
          :empty-text="departmentPresentation.todoEmptyText"
        />
      </aside>
    </div>
  </div>
</template>

<style scoped>
/*
 * 容器查询只能匹配后代元素，元素不能查询自己的容器。
 * 所以容器声明在门户根节点 `.rrn-portal` 上，`portal.css` 里的
 * `@container portal-page (...)` 规则作用于它内部的后代。
 */
.rrn-portal {
  container: portal-page / inline-size;
}
</style>

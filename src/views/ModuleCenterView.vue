<script setup lang="ts">
import { Plus, Search, X } from '@lucide/vue'
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
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
import HomePrismArtwork from '@/components/portal/HomePrismArtwork.vue'
import HomeAppearanceControl from '@/components/portal/HomeAppearanceControl.vue'
import HomePreviewRegion from '@/components/portal/HomePreviewRegion.vue'
import { homePaletteStyle } from '@/components/portal/homePrismPresentation'
import { useHomeAppearance, homeSearchKey } from '@/composables/useHomeAppearance'
import { useHomePresentation, canPreviewModule } from '@/composables/useHomePresentation'
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
  ...homePaletteStyle(currentDepartmentId.value),
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
      // 新 UV 工作区仅属于华康 A，不采用集团厂区兜底。
      if (module.id === 'uv-printing' && appStore.activeFactoryId !== 'huakang-a') return false
      if (module.id === 'spray-production' && !isSprayFactory(appStore.activeFactoryId)) return false
      if (module.factoryIds?.length && !module.factoryIds.includes(factory.id)) return false
      if (currentDepartmentId.value === 'pmc-warehouse' && module.id === 'carton-procurement'
        && !authStore.can('carton_procurement:read', factory.id)) return false
      if (
        module.strictAccess
        && module.permissions?.length
        && !authStore.canAny(module.permissions, factory.id, module.permissionDepartment)
      ) return false
      return true
    })
    .map((module) => {
    const scopedModule = getFactoryScopedModule(module, factory.id)

    if (currentDepartmentId.value === 'pmc-warehouse') {
      if (module.id === 'carton-supplier') {
        const internal = authStore.can('carton_procurement:read', factory.id)
        const supplier = authStore.can('carton_supplier:read', factory.id, '*')
        return { ...scopedModule, route: supplier ? '/carton-supplier'
          : internal ? getFactoryScopedRoute('/carton-supplier-management', factory.id) : '/carton-supplier' }
      }
      if (module.id === 'carton-mark-check' && !authStore.can('carton_mark:read', factory.id)) {
        return { ...scopedModule, route: '/carton-supplier/carton-mark',
          summary: '查看并下载与本厂已发行采购单关联、已核对可用的箱唛 Excel 和 PDF',
          status: '供应商只读', statusTone: 'teal' as const, todos: [],
          children: scopedModule.children.filter(child => ['客人 Excel', '印刷 PDF'].includes(child.label)) }
      }
    }

    if (module.id === 'uv-printing') {
      const authorized = authStore.can('uv_ops:read', factory.id, 'production')
      return {...scopedModule, summary:'机台现场、任务排程、班次核数、品质交接与材料核算',
        status:authorized ? '工作区' : '权限待开通', statusTone:'teal' as const,
        stats:authorized ? '进入华康 A 工作区' : '需要华康 A 生产部授权', detailPage:authorized,
        route:authorized ? getFactoryScopedRoute('/modules/production/uv-printing/live', factory.id) : undefined}
    }

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

const { density, effectiveMotion } = useHomeAppearance()
const scope = computed(() => JSON.stringify([authStore.currentUser?.id, appStore.activeFactoryId, appStore.activeProductionFactory.id, currentDepartmentId.value]))
const { input, query, composing, filteredModules, featuredModule, pinnedId, dialogOpen, clearSearch, commitSearch, preview, pin, unpin, cancelPreview } = useHomePresentation(visibleModules, scope)
const containerRef = ref<HTMLElement | null>(null)
const searchRef = ref<HTMLInputElement | null>(null)
const opener = ref<HTMLElement | null>(null)
const narrow = ref(false)
const revealing = ref(true)
const searchRequest = inject(homeSearchKey, ref(0))
let resizeObserver: ResizeObserver | undefined
let revealTimer: ReturnType<typeof setTimeout> | undefined
function focusSearch() { searchRef.value?.focus(); searchRef.value?.scrollIntoView?.({ block: 'nearest' }) }
function openPreview(id: string, event: MouseEvent) {
  opener.value = event.currentTarget as HTMLElement
  if (pin(id) && narrow.value) dialogOpen.value = true
}
function shortcut(event: KeyboardEvent) {
  if (event.key !== '/' || event.isComposing || composing.value || event.ctrlKey || event.altKey || event.metaKey) return
  const target = event.target as HTMLElement | null
  if (target?.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])') || document.querySelector('[role="dialog"], [data-reka-popper-content-wrapper]')) return
  event.preventDefault(); focusSearch()
}
function stopHiddenPreview() { if (document.hidden) cancelPreview() }
onMounted(() => {
  revealTimer = setTimeout(() => { revealing.value = false }, 600)
  document.addEventListener('keydown', shortcut)
  document.addEventListener('visibilitychange', stopHiddenPreview)
  if (typeof ResizeObserver !== 'undefined' && containerRef.value) {
    resizeObserver = new ResizeObserver(entries => { narrow.value = (entries[0]?.contentRect.width ?? 1000) < 640 })
    resizeObserver.observe(containerRef.value)
  }
})
watch(searchRequest, () => void nextTick(focusSearch))
onBeforeUnmount(() => {
  clearTimeout(revealTimer); resizeObserver?.disconnect()
  document.removeEventListener('keydown', shortcut)
  document.removeEventListener('visibilitychange', stopHiddenPreview)
})

watch(currentDepartmentId, (departmentId) => {
  appStore.setActiveDepartment(departmentId)
}, { immediate: true })
</script>

<template>
  <div ref="containerRef" class="rrn-home-container">
  <div class="rrn-portal rrn-home app-page space-y-6" data-portal-ui="jade-v3" data-home-experience="prism-v4" :data-home-motion="effectiveMotion" :data-home-density="density" :data-department="currentDepartmentId" :style="portalRootStyle">
    <PortalHero eyebrow="Department Workspace" :title="title" :description="departmentEntry.heroSubtitle" :motif="departmentPresentation.motif" pending-note="新增系统模块暂未接入">
      <template #artwork><HomePrismArtwork :identity="currentDepartmentId" /></template>
      <template #actions><HomeAppearanceControl /><Button type="button" size="lg" disabled><Plus class="size-4" aria-hidden="true" />新增系统模块</Button></template>
    </PortalHero>
    <DepartmentTabs home-experience />
    <div class="home-department-layout">
      <SectionPanel class="portal-section home-module-section" :title="departmentEntry.panelTitle" :subtitle="departmentEntry.panelSubtitle">
        <div class="home-search-toolbar">
          <div class="home-search-field">
            <label for="home-module-search">搜索本部门入口</label>
            <div class="home-search-input"><Search :size="18" aria-hidden="true" />
              <input id="home-module-search" ref="searchRef" :value="input" type="search" autocomplete="off" placeholder="模块名称、功能说明或标签" @input="commitSearch(($event.target as HTMLInputElement).value)" @compositionstart="composing = true" @compositionend="composing = false; commitSearch(($event.target as HTMLInputElement).value)" @keydown.esc.stop.prevent="clearSearch">
              <button v-if="input" type="button" aria-label="清除入口搜索" @click="clearSearch(); focusSearch()"><X :size="16" aria-hidden="true" /></button>
            </div>
          </div>
          <div class="home-segmented" role="group" aria-label="显示密度"><button type="button" :aria-pressed="density === 'comfortable'" @click="density = 'comfortable'">舒适</button><button type="button" :aria-pressed="density === 'compact'" @click="density = 'compact'">紧凑</button></div>
          <p class="home-search-count" role="status" aria-live="polite">{{ query ? `找到 ${filteredModules.length} 个入口` : `${visibleModules.length} 个可见模块 · 当前厂区目录` }}</p>
        </div>
        <TransitionGroup name="home-filter" tag="div" class="portal-module-grid" :data-module-count="filteredModules.length" :css="effectiveMotion !== 'off'">
          <div v-for="(module, index) in filteredModules" :key="`${scope}:${module.id}`" class="home-grid-item">
            <div class="home-card-reveal" :data-reveal="revealing && !query" :style="{ '--home-index': index }">
              <ModuleCard :module="module" :index="index" :active="featuredModule?.id === module.id" :pinned="pinnedId === module.id" :previewable="canPreviewModule(module)" :search-query="query" @preview="openPreview(module.id, $event)" @peek="!narrow && preview(module.id)" @cancel-peek="cancelPreview" @focus-preview="!narrow && preview(module.id, true)" />
            </div>
          </div>
        </TransitionGroup>
        <div v-if="!filteredModules.length" class="home-empty" role="status"><h3>{{ visibleModules.length ? '没有找到匹配的入口' : '当前厂区没有可显示的模块' }}</h3><p>{{ visibleModules.length ? '试试模块名称、功能说明或标签，也可以清除搜索。' : '请核对当前厂区与账号授权，目录将按可用范围显示。' }}</p><button v-if="query" type="button" class="home-preview-button" @click="clearSearch">清除搜索</button></div>
        <div class="portal-candidates"><h3 class="portal-candidates__title">推荐下一批模块</h3><p class="portal-candidates__list">{{ departmentEntry.quickCandidates.join('、') }}</p><div class="portal-candidates__meter"><ProgressMeter :value="58" :tone="currentDepartmentId === 'production' ? 'amber' : 'teal'" /></div><p class="portal-candidates__note">规划示意，不代表已完成比例 · {{ currentDepartment.focus }}</p></div>
      </SectionPanel>
      <aside class="home-aside" @pointerenter="cancelPreview">
        <HomePreviewRegion v-if="visibleModules.length" v-model:open="dialogOpen" :module="featuredModule" :pinned="Boolean(pinnedId)" :searching="Boolean(query)" :narrow="narrow" :identity="currentDepartmentId" :opener="opener" @unpin="unpin" />
        <PermissionMatrix appearance="portal" :rows="departmentEntry.permissionRows" :note="departmentPresentation.permissionNote" />
        <TodoQueue appearance="portal" subtitle="目录待办示例 · 实际事项请进入业务模块" :items="visibleDepartmentTodos" :empty-text="departmentPresentation.todoEmptyText" />
      </aside>
    </div>
  </div>
  </div>
</template>

<style scoped>
/* This ancestor is intentionally distinct from the child being queried. */
.rrn-home-container { container: home-page / inline-size; min-width: 0; }
.rrn-portal { container: portal-page / inline-size; }
</style>

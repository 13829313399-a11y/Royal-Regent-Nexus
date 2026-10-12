<script setup lang="ts">
import { Plus, Search, X } from '@lucide/vue'
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  departmentMap,
  departmentModuleRegistry,
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
import { useVisibleModules } from '@/composables/useVisibleModules'
import { useHomePresentation, canPreviewModule } from '@/composables/useHomePresentation'
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

const visibleModules = useVisibleModules(currentDepartmentId)

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

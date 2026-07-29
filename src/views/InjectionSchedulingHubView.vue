<script setup lang="ts">
import {
  AlertTriangle,
  ArrowLeft,
  Bell,
  Boxes,
  CloudOff,
  Database,
  Expand,
  FileUp,
  LogOut,
  Rocket,
  Scale,
  Sparkles,
} from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import CompactMachineBoard from '@/components/injection-scheduling/CompactMachineBoard.vue'
import ScheduleTimeline from '@/components/injection-scheduling/ScheduleTimeline.vue'
import SchedulingFilters from '@/components/injection-scheduling/SchedulingFilters.vue'
import SchedulingImportDialog from '@/components/injection-scheduling/SchedulingImportDialog.vue'
import SchedulingKpiGrid from '@/components/injection-scheduling/SchedulingKpiGrid.vue'
import SchedulingOverlays from '@/components/injection-scheduling/SchedulingOverlays.vue'
import {
  factoryContexts,
  getFactoryScopedRoute,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
} from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'
import { useInjectionSchedulingStore } from '@/stores/injectionScheduling'
import type {
  SchedulingDensity,
  SchedulingFilters as SchedulingFilterState,
  SchedulingKpi,
  SchedulingViewMode,
} from '@/types/injectionScheduling'

const route = useRoute()
const appStore = useAppStore()
const store = useInjectionSchedulingStore()
const hubRoot = ref<HTMLElement | null>(null)
let toastTimer: ReturnType<typeof window.setTimeout> | undefined

const selectedFactoryId = computed<ProductionFactoryContextId>(() => {
  const routeFactory = Array.isArray(route.query.factory) ? route.query.factory[0] : route.query.factory
  if (typeof routeFactory === 'string' && isProductionFactoryContextId(routeFactory)) return routeFactory
  return isProductionFactoryContextId(appStore.activeProductionFactory.id)
    ? appStore.activeProductionFactory.id
    : 'huaxing'
})

const activeFactory = computed(() => factoryContexts.find((factory) => factory.id === selectedFactoryId.value)
  ?? factoryContexts.find((factory) => factory.id === 'huaxing')!)
const productionCenterRoute = computed(() => getFactoryScopedRoute('/modules/production', selectedFactoryId.value))
const pageRouteForFactory = (factoryId: ProductionFactoryContextId) => getFactoryScopedRoute(
  '/modules/production/injection-scheduling',
  factoryId,
)

function updateViewMode(value: SchedulingViewMode) {
  store.viewMode = value
}

function updateDensity(value: SchedulingDensity) {
  store.density = value
}

function updateFilters(value: SchedulingFilterState) {
  store.filters = value
}

function activateKpi(action: NonNullable<SchedulingKpi['action']>) {
  if (action === 'backlog') store.openBacklog()
  if (action === 'alerts') store.alertsOpen = true
}

function requestTaskMove(taskId: string, targetMachineId: string) {
  const task = store.tasks.find((item) => item.id === taskId)
  store.requestMove({
    taskId,
    sourceMachineId: task?.machineId,
    targetMachineId,
  })
}

function requestBacklogAssignment(backlogId: string, targetMachineId: string) {
  store.requestMove({ backlogId, targetMachineId })
}

async function enterBigScreen() {
  store.bigScreen = true
  try {
    await hubRoot.value?.requestFullscreen?.()
  } catch {
    // CSS big-screen mode still works when fullscreen policy blocks the browser API.
  }
}

async function exitBigScreen() {
  store.bigScreen = false
  if (document.fullscreenElement) {
    try {
      await document.exitFullscreen()
    } catch {
      // The visible mode has already been restored.
    }
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  if (store.bigScreen) {
    void exitBigScreen()
    return
  }
  store.closeTransientLayers()
}

function handleFullscreenChange() {
  if (!document.fullscreenElement) store.bigScreen = false
}

watch(selectedFactoryId, (factoryId) => {
  void store.load(factoryId)
}, { immediate: true })

watch(() => store.toast?.id, () => {
  if (toastTimer) window.clearTimeout(toastTimer)
  if (store.toast) toastTimer = window.setTimeout(() => store.clearToast(), 3600)
})

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  document.addEventListener('fullscreenchange', handleFullscreenChange)
})

onBeforeUnmount(() => {
  if (toastTimer) window.clearTimeout(toastTimer)
  window.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
})
</script>

<template>
  <div
    ref="hubRoot"
    class="injection-hub-root grid h-dvh min-h-0 grid-rows-[50px_minmax(0,1fr)] overflow-hidden bg-[#eef5f3] text-slate-950"
    :class="store.bigScreen ? 'big-screen-mode !bg-[#071a19]' : ''"
  >
    <header class="flex min-w-0 items-center border-b border-slate-200 bg-white px-4 shadow-sm">
      <div class="flex min-w-0 items-center gap-2.5">
        <span class="grid size-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-teal-700 to-teal-950 text-white shadow-sm">
          <Boxes class="size-4" />
        </span>
        <div class="min-w-0">
          <strong class="block truncate text-[14px] font-black">Royal Regent Nexus</strong>
          <span class="block truncate text-[8px] text-slate-500">华登集团 · 快速扩展与异常治理厂区</span>
        </div>
      </div>

      <nav class="mx-auto hidden items-center gap-1.5 md:flex" aria-label="切换厂区">
        <RouterLink
          v-for="factory in factoryContexts"
          :key="factory.id"
          :to="pageRouteForFactory(factory.id as ProductionFactoryContextId)"
          class="inline-flex h-8 items-center rounded-lg border px-3 text-[10px] font-black transition"
          :class="selectedFactoryId === factory.id ? 'border-teal-700 bg-teal-700 text-white shadow-sm' : 'border-slate-200 bg-white text-slate-600 hover:border-teal-200'"
        >
          {{ factory.shortName }}
        </RouterLink>
      </nav>

      <div class="ml-auto flex items-center gap-2">
        <button type="button" class="grid size-8 place-items-center rounded-lg border border-slate-200 text-slate-500" aria-label="通知"><Bell class="size-3.5" /></button>
        <AccountMenu compact />
      </div>
    </header>

    <main class="workspace-grid grid min-h-0 grid-rows-[48px_58px_44px_minmax(0,1fr)_26px] gap-1.5 overflow-hidden p-2">
      <section class="flex min-w-0 items-center gap-3 overflow-hidden rounded-xl bg-gradient-to-r from-[#0d4944] via-[#0b5d55] to-[#0a776b] px-3 text-white shadow-sm">
        <RouterLink :to="productionCenterRoute" class="grid size-8 shrink-0 place-items-center rounded-lg border border-white/15 bg-white/5" aria-label="返回生产部模块中心"><ArrowLeft class="size-4" /></RouterLink>
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h1 class="truncate text-[16px] font-black">{{ activeFactory.shortName }}注塑排产中枢</h1>
            <span v-if="store.hasPreviewData" class="rounded-full border border-teal-300/30 bg-white/10 px-2 py-0.5 text-[8px] font-black">{{ store.sourceMode === 'backend' ? '正式后端' : 'Mock 快照' }}</span>
            <span class="rounded-full border border-white/15 bg-white/5 px-2 py-0.5 text-[8px] font-black">{{ store.plan.label }} · r{{ store.plan.revision }}</span>
          </div>
          <p class="mt-0.5 truncate text-[8px] text-teal-100">
            {{ store.hasPreviewData ? `${store.sourceLabel} · 当前生产、后续模具队列与交期风险` : '公共模块已建立，等待导入该厂区独立排程数据' }}
          </p>
        </div>
        <div class="ml-auto flex shrink-0 items-center gap-1.5">
          <button v-if="!store.bigScreen && store.supportsWorkbookImport" type="button" class="module-action" @click="store.openImport"><FileUp class="size-3" />导入计划表</button>
          <button v-if="!store.bigScreen" type="button" class="module-action" @click="store.rulesOpen = true"><Scale class="size-3" />规则与约束</button>
          <button v-if="!store.bigScreen && store.hasPreviewData" type="button" class="module-action" @click="store.generateSuggestion"><Sparkles class="size-3" />智能排程</button>
          <button v-if="!store.bigScreen && store.hasPreviewData" type="button" class="module-action" @click="store.openBacklog"><Boxes class="size-3" />待排池 {{ store.backlog.length }}</button>
          <button v-if="!store.bigScreen" type="button" class="module-action" @click="enterBigScreen"><Expand class="size-3" />大屏模式</button>
          <button v-if="!store.bigScreen && store.hasPreviewData" type="button" class="module-action bg-teal-100 !text-teal-950 hover:bg-white" @click="store.publishOpen = true"><Rocket class="size-3" />发布大屏</button>
          <button v-else-if="store.bigScreen" type="button" class="module-action" @click="exitBigScreen"><LogOut class="size-3" />退出大屏</button>
        </div>
      </section>

      <template v-if="store.loading">
        <section class="grid grid-cols-3 gap-2 xl:grid-cols-6"><i v-for="index in 6" :key="index" class="skeleton-shimmer rounded-xl border border-slate-200" /></section>
        <div class="skeleton-shimmer rounded-xl border border-slate-200" />
        <div class="skeleton-shimmer rounded-xl border border-slate-200" />
      </template>

      <template v-else-if="store.hasPreviewData">
        <SchedulingKpiGrid v-if="!store.bigScreen" :kpis="store.kpis" @activate="activateKpi" />

        <SchedulingFilters
          v-if="!store.bigScreen"
          :view-mode="store.viewMode"
          :density="store.density"
          :filters="store.filters"
          :backlog-count="store.backlog.length"
          @update:view-mode="updateViewMode"
          @update:density="updateDensity"
          @update:filters="updateFilters"
          @open-backlog="store.openBacklog"
          @enter-big-screen="enterBigScreen"
        />

        <CompactMachineBoard
          v-if="store.viewMode === 'board' || store.bigScreen"
          :machines="store.visibleMachines"
          :tasks-by-machine="store.tasksByMachine"
          :density="store.density"
          :big-screen="store.bigScreen"
          @select-task="store.selectTask"
          @select-machine="store.selectMachine"
          @request-move="requestTaskMove"
          @nudge-task="store.nudgeTask"
          @open-backlog="store.openBacklog"
        />
        <ScheduleTimeline
          v-else
          :machines="store.visibleMachines"
          :tasks-by-machine="store.tasksByMachine"
          @select-task="store.selectTask"
        />

        <footer class="flex min-w-0 items-center gap-4 rounded-lg border border-slate-200 bg-white px-3 text-[8px] text-slate-500" :class="store.bigScreen ? '!border-slate-800 !bg-[#0b2321] !text-slate-400' : ''">
          <span class="inline-flex items-center gap-1.5">
            <i class="size-1.5 rounded-full bg-teal-500" />
            {{ store.sourceMode === 'backend' ? (store.plan.status === 'published' ? '正式后端 · 已发布' : '正式后端草案') : '浏览器 Mock 草案' }}
          </span>
          <span>数据快照：{{ store.snapshotAt }}</span>
          <span>厂区隔离：{{ activeFactory.shortName }}</span>
          <span v-if="store.sourceMode === 'backend'" class="ml-auto inline-flex items-center gap-1.5 text-teal-700"><Database class="size-3" />后端已接入 · revision 受控</span>
          <span v-else class="ml-auto inline-flex items-center gap-1.5"><CloudOff class="size-3 text-amber-600" />Mock 降级 · 未写生产数据库</span>
          <button type="button" class="font-black text-red-600" @click="store.alertsOpen = true"><AlertTriangle class="inline size-3" /> 异常</button>
        </footer>
      </template>

      <template v-else>
        <section class="col-span-full row-span-3 grid min-h-0 place-items-center rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <div class="max-w-md">
            <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-slate-100 text-slate-500"><Boxes class="size-6" /></span>
            <h2 class="mt-5 text-xl font-black text-slate-900">{{ activeFactory.shortName }}暂未建立注塑排程快照</h2>
            <p class="mt-3 text-sm leading-6 text-slate-500">华兴与华康 B 使用各自独立 Mock；当前厂区不会回退显示其他厂区数据。正式接入必须由后端按 factoryId 强制隔离。</p>
            <button v-if="store.supportsWorkbookImport" type="button" class="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-black text-white" @click="store.openImport"><FileUp class="size-4" />导入该厂区计划表</button>
            <RouterLink :to="productionCenterRoute" class="mt-6 inline-flex h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-black text-white"><ArrowLeft class="size-4" />返回生产部模块中心</RouterLink>
          </div>
        </section>
        <footer class="col-span-full flex items-center rounded-lg border border-slate-200 bg-white px-3 text-[8px] text-slate-500">等待 {{ activeFactory.shortName }} 厂区独立数据接入</footer>
      </template>
    </main>

    <SchedulingOverlays
      :selected-task="store.selectedTask"
      :selected-machine="store.selectedMachine"
      :selected-backlog="store.selectedBacklog"
      :machines="store.machines"
      :tasks="store.tasks"
      :pending-move="store.pendingMove"
      :pending-move-validation="store.pendingMoveValidation"
      :backlog="store.visibleBacklog"
      :alerts-open="store.alertsOpen"
      :rules-open="store.rulesOpen"
      :publish-open="store.publishOpen"
      :backlog-open="store.backlogOpen"
      :optimizer-open="store.optimizerOpen"
      :optimization-result="store.optimizationResult"
      :plan="store.plan"
      :factory-name="activeFactory.shortName"
      :backend-connected="store.sourceMode === 'backend'"
      @close-task="store.selectedTaskId = ''"
      @close-machine="store.selectedMachineId = ''"
      @select-backlog="store.selectBacklog"
      @clear-backlog-selection="store.selectedBacklogId = ''"
      @assign-backlog="requestBacklogAssignment"
      @close-backlog="store.backlogOpen = false; store.selectedBacklogId = ''"
      @cancel-move="store.cancelMove"
      @confirm-move="store.confirmMove"
      @close-alerts="store.alertsOpen = false"
      @close-rules="store.rulesOpen = false"
      @close-publish="store.publishOpen = false"
      @close-optimizer="store.optimizerOpen = false"
      @apply-optimizer="store.applySuggestion"
      @publish="store.publishPreview"
    />

    <SchedulingImportDialog
      :open="store.importOpen"
      :busy="store.importBusy"
      :error="store.importError"
      :preview="store.importPreview"
      :factory-name="activeFactory.shortName"
      @close="store.closeImport"
      @preview="store.previewWorkbook"
      @confirm="store.confirmWorkbook"
    />

    <Transition name="injection-toast">
      <aside
        v-if="store.toast"
        class="fixed bottom-5 right-5 z-[95] flex w-[min(390px,calc(100vw-40px))] items-start gap-3 rounded-xl border bg-white p-4 shadow-2xl"
        :class="store.toast.tone === 'teal' ? 'border-teal-200' : 'border-amber-200'"
        role="status"
        aria-live="polite"
      >
        <span class="grid size-9 shrink-0 place-items-center rounded-lg" :class="store.toast.tone === 'teal' ? 'bg-teal-50 text-teal-700' : 'bg-amber-50 text-amber-700'"><Sparkles class="size-4" /></span>
        <div class="min-w-0"><strong class="text-sm text-slate-900">{{ store.toast.title }}</strong><p class="mt-1 text-xs leading-5 text-slate-500">{{ store.toast.detail }}</p></div>
      </aside>
    </Transition>
  </div>
</template>

<style scoped>
.module-action {
  display: inline-flex;
  height: 30px;
  align-items: center;
  gap: 6px;
  border: 1px solid rgb(255 255 255 / 16%);
  border-radius: 9px;
  padding: 0 10px;
  color: white;
  font-size: 9px;
  font-weight: 900;
  transition: background-color 160ms ease;
}
.module-action:hover { background: rgb(255 255 255 / 10%); }
.big-screen-mode {
  grid-template-rows: 44px minmax(0,1fr);
  color-scheme: dark;
}
.big-screen-mode .workspace-grid {
  grid-template-rows: 48px minmax(0,1fr) 26px;
  gap: 5px;
  padding: 5px 7px;
}
.injection-toast-enter-active,
.injection-toast-leave-active { transition: opacity 180ms ease, transform 180ms ease; }
.injection-toast-enter-from,
.injection-toast-leave-to { opacity: 0; transform: translateY(8px); }
@media (max-width: 1080px) {
  .workspace-grid { grid-template-rows: 48px 58px 44px minmax(0,1fr) 26px; }
}
@media (prefers-reduced-motion: reduce) {
  .injection-toast-enter-active,
  .injection-toast-leave-active { transition: none; }
}
</style>

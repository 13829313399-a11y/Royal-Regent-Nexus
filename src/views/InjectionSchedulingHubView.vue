<script setup lang="ts">
import {
  AlertTriangle,
  ArrowLeft,
  Boxes,
  Building2,
  CalendarClock,
  CircleDashed,
  CloudOff,
  FileWarning,
  RefreshCcw,
  Rocket,
  Scale,
  Sparkles,
} from '@lucide/vue'
import { computed, onBeforeUnmount, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import BacklogPool from '@/components/injection-scheduling/BacklogPool.vue'
import MachineScheduleBoard from '@/components/injection-scheduling/MachineScheduleBoard.vue'
import ScheduleTimeline from '@/components/injection-scheduling/ScheduleTimeline.vue'
import SchedulingFilters from '@/components/injection-scheduling/SchedulingFilters.vue'
import SchedulingKpiGrid from '@/components/injection-scheduling/SchedulingKpiGrid.vue'
import SchedulingOverlays from '@/components/injection-scheduling/SchedulingOverlays.vue'
import { Button } from '@/components/ui/button'
import {
  factoryContexts,
  getFactoryScopedRoute,
  isProductionFactoryContextId,
  type ProductionFactoryContextId,
} from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'
import { useInjectionSchedulingStore } from '@/stores/injectionScheduling'
import type { SchedulingFilters as SchedulingFilterState, SchedulingViewMode } from '@/types/injectionScheduling'

const route = useRoute()
const appStore = useAppStore()
const store = useInjectionSchedulingStore()
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
const machineMap = computed(() => new Map(store.machines.map((machine) => [machine.id, machine])))
const pendingMoveLabel = computed(() => {
  if (!store.pendingMove) return ''
  const target = machineMap.value.get(store.pendingMove.targetMachineId)?.name ?? store.pendingMove.targetMachineId
  return `目标机台：${target}`
})

function updateViewMode(value: SchedulingViewMode) {
  store.viewMode = value
}

function updateFilters(value: SchedulingFilterState) {
  store.filters = value
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

watch(selectedFactoryId, (factoryId) => {
  void store.load(factoryId)
}, { immediate: true })

watch(() => store.toast?.id, () => {
  if (toastTimer) window.clearTimeout(toastTimer)
  if (store.toast) toastTimer = window.setTimeout(() => store.clearToast(), 3600)
})

onBeforeUnmount(() => {
  if (toastTimer) window.clearTimeout(toastTimer)
})
</script>

<template>
  <div class="min-h-screen bg-[#f3f6f7] text-slate-950">
    <header class="sticky top-0 z-40 border-b border-teal-950 bg-[#102f2d] text-white shadow-sm">
      <div class="mx-auto flex min-h-[62px] w-full max-w-[1880px] items-center gap-3 px-4 py-2.5 sm:px-6">
        <RouterLink
          :to="productionCenterRoute"
          class="inline-flex h-9 items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 text-xs font-bold text-teal-50 transition hover:bg-white/10"
        >
          <ArrowLeft class="size-4" aria-hidden="true" />
          <span class="hidden sm:inline">生产部模块中心</span>
        </RouterLink>

        <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-teal-600 text-white shadow-lg shadow-teal-950/25">
          <Boxes class="size-[18px]" aria-hidden="true" />
        </span>
        <div class="min-w-0">
          <strong class="block truncate text-sm font-black">注塑排产中枢</strong>
          <span class="block truncate text-[10px] text-teal-200">Royal Regent Nexus</span>
        </div>

        <span class="ml-2 hidden h-8 items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 text-[11px] font-semibold text-teal-50 min-[1400px]:inline-flex">
          <Building2 class="size-3.5" aria-hidden="true" />
          {{ activeFactory.shortName }}厂区 · 啤机部
        </span>

        <div class="flex-1" />

        <button type="button" class="hidden h-9 items-center gap-2 rounded-lg border border-white/15 px-3 text-xs font-bold text-white hover:bg-white/10 md:inline-flex" @click="store.rulesOpen = true">
          <Scale class="size-3.5" aria-hidden="true" />排程规则
        </button>
        <button type="button" class="hidden h-9 items-center gap-2 rounded-lg border border-white/15 px-3 text-xs font-bold text-white hover:bg-white/10 md:inline-flex" @click="store.generateSuggestion">
          <Sparkles class="size-3.5" aria-hidden="true" />生成建议排程
        </button>
        <button type="button" class="inline-flex h-9 items-center gap-2 rounded-lg bg-teal-600 px-3 text-xs font-black text-white shadow hover:bg-teal-500" @click="store.publishOpen = true">
          <Rocket class="size-3.5" aria-hidden="true" />发布计划
        </button>
        <AccountMenu compact />
      </div>
    </header>

    <main class="mx-auto w-full max-w-[1880px] space-y-4 px-4 py-4 sm:px-6">
      <section
        v-if="store.isHuaxingPreview"
        class="flex flex-wrap items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900"
      >
        <FileWarning class="size-4 shrink-0 text-amber-700" aria-hidden="true" />
        <p class="min-w-[260px] flex-1"><strong>数据日期提示：</strong>{{ store.notice }}</p>
        <button type="button" class="inline-flex h-8 items-center gap-2 rounded-lg border border-amber-200 bg-white px-3 font-bold hover:bg-amber-100" @click="store.markRecalculate">
          <RefreshCcw class="size-3.5" aria-hidden="true" />标记重算
        </button>
      </section>

      <section class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <div class="flex flex-wrap items-center gap-2">
            <h1 class="text-2xl font-black tracking-tight text-slate-950 sm:text-[30px]">{{ activeFactory.shortName }}注塑生产日计划</h1>
            <span class="rounded-full border border-teal-200 bg-teal-50 px-2.5 py-1 text-[10px] font-black text-teal-700">前端预览</span>
            <span class="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-black text-slate-500">{{ store.version }}</span>
          </div>
          <p class="mt-2 text-sm text-slate-500">按机台查看正在啤制的产品、后续模具队列、交期风险与待排订单。</p>
        </div>
        <div v-if="store.isHuaxingPreview" class="text-right text-[10px] leading-5 text-slate-500">
          <p>来源：{{ store.sourceLabel }}</p>
          <p>计划表快照 · {{ store.snapshotAt }}</p>
        </div>
      </section>

      <template v-if="store.loading">
        <section class="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6" aria-label="正在加载排程">
          <div v-for="index in 6" :key="index" class="skeleton-shimmer h-28 rounded-xl border border-slate-200" />
        </section>
        <div class="skeleton-shimmer h-14 rounded-xl border border-slate-200" />
        <div class="skeleton-shimmer h-[460px] rounded-xl border border-slate-200" />
      </template>

      <template v-else-if="store.isHuaxingPreview">
        <SchedulingKpiGrid :kpis="store.kpis" />

        <SchedulingFilters
          :view-mode="store.viewMode"
          :filters="store.filters"
          :backlog-count="store.backlog.length"
          :details-expanded="store.detailsExpanded"
          @update:view-mode="updateViewMode"
          @update:filters="updateFilters"
          @update:details-expanded="store.detailsExpanded = $event"
        />

        <MachineScheduleBoard
          v-if="store.viewMode === 'board'"
          :machines="store.visibleMachines"
          :tasks="store.tasks"
          :details-expanded="store.detailsExpanded"
          @select-task="store.selectTask"
          @request-move="requestTaskMove"
        />
        <ScheduleTimeline
          v-else-if="store.viewMode === 'timeline'"
          :machines="store.visibleMachines"
          :tasks="store.tasks"
          @select-task="store.selectTask"
        />
        <BacklogPool
          v-else
          :orders="store.visibleBacklog"
          :machines="store.machines"
          :selected-order="store.selectedBacklog"
          @select="store.selectBacklog"
          @assign="requestBacklogAssignment"
        />

        <footer class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-[10px] text-slate-500">
          <span class="inline-flex items-center gap-2"><CloudOff class="size-3.5 text-amber-600" aria-hidden="true" />Mock 数据只保存在当前浏览器内，不会写入生产数据库。</span>
          <button type="button" class="inline-flex items-center gap-2 font-bold text-red-600 hover:text-red-700" @click="store.alertsOpen = true">
            <AlertTriangle class="size-3.5" aria-hidden="true" />查看 130 项交期异常
          </button>
        </footer>
      </template>

      <section v-else class="grid min-h-[520px] place-items-center rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <div class="max-w-md">
          <span class="mx-auto grid size-14 place-items-center rounded-2xl bg-slate-100 text-slate-500">
            <CircleDashed class="size-6" aria-hidden="true" />
          </span>
          <h2 class="mt-5 text-xl font-black text-slate-900">{{ activeFactory.shortName }}暂未建立注塑排程快照</h2>
          <p class="mt-3 text-sm leading-6 text-slate-500">当前前端演示数据仅属于华兴厂区。为避免跨厂区数据混用，本页不会回退显示华兴 Mock 数据。</p>
          <Button as-child class="mt-6">
            <RouterLink :to="productionCenterRoute"><ArrowLeft class="size-4" />返回生产部模块中心</RouterLink>
          </Button>
        </div>
      </section>
    </main>

    <SchedulingOverlays
      :selected-task="store.selectedTask"
      :machines="store.machines"
      :pending-move="store.pendingMove"
      :backlog="store.backlog"
      :alerts-open="store.alertsOpen"
      :rules-open="store.rulesOpen"
      :publish-open="store.publishOpen"
      @close-task="store.selectedTaskId = ''"
      @cancel-move="store.cancelMove"
      @confirm-move="store.confirmMove"
      @close-alerts="store.alertsOpen = false"
      @close-rules="store.rulesOpen = false"
      @close-publish="store.publishOpen = false"
      @publish="store.publishPreview"
    />

    <Transition name="injection-toast">
      <aside
        v-if="store.toast"
        class="fixed bottom-5 right-5 z-[90] flex w-[min(390px,calc(100vw-40px))] items-start gap-3 rounded-xl border bg-white p-4 shadow-2xl"
        :class="store.toast.tone === 'teal' ? 'border-teal-200' : 'border-amber-200'"
        role="status"
        aria-live="polite"
      >
        <span class="grid size-9 shrink-0 place-items-center rounded-lg" :class="store.toast.tone === 'teal' ? 'bg-teal-50 text-teal-700' : 'bg-amber-50 text-amber-700'">
          <CalendarClock class="size-4" aria-hidden="true" />
        </span>
        <div class="min-w-0">
          <strong class="text-sm text-slate-900">{{ store.toast.title }}</strong>
          <p class="mt-1 text-xs leading-5 text-slate-500">{{ store.toast.detail }}</p>
        </div>
      </aside>
    </Transition>
  </div>
</template>

<style scoped>
.injection-toast-enter-active,
.injection-toast-leave-active { transition: opacity 180ms ease, transform 180ms ease; }
.injection-toast-enter-from,
.injection-toast-leave-to { opacity: 0; transform: translateY(8px); }
</style>

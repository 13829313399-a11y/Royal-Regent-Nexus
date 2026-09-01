<script setup lang="ts">
import {
  ArrowLeft,
  CalendarRange,
  Columns3,
  Download,
  Filter,
  ListTree,
  RefreshCw,
  Search,
  Save,
  ShieldCheck,
} from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import { injectionSchedulingApi } from '@/api/injectionScheduling'
import InjectionScheduleBoard from '@/features/injection-scheduling/components/InjectionScheduleBoard.vue'
import InjectionScheduleKpis from '@/features/injection-scheduling/components/InjectionScheduleKpis.vue'
import InjectionScheduleImportPanel from '@/features/injection-scheduling/components/InjectionScheduleImportPanel.vue'
import InjectionScheduleOperationsPanel from '@/features/injection-scheduling/components/InjectionScheduleOperationsPanel.vue'
import InjectionScheduleTable from '@/features/injection-scheduling/components/InjectionScheduleTable.vue'
import { useInjectionScheduleWorkspace } from '@/features/injection-scheduling/composables/useInjectionScheduleWorkspace'
import {
  factoryContexts,
  type ProductionFactoryContextId,
} from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'
import { getApiErrorMessage } from '@/lib/http'
import type { InjectionScheduleSavedView } from '@/types/injectionScheduling'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const injectionFactoryIds = ['huakang-a', 'huakang-b', 'huadeng', 'huaxing'] as const
type InjectionFactoryId = typeof injectionFactoryIds[number]

function isInjectionFactoryId(value: string): value is InjectionFactoryId {
  return injectionFactoryIds.includes(value as InjectionFactoryId)
}

const factoryId = computed(() => {
  const requested = Array.isArray(route.query.factory) ? route.query.factory[0] : route.query.factory
  if (typeof requested === 'string' && isInjectionFactoryId(requested)) return requested
  const activeFactoryId = appStore.activeProductionFactory.id
  return isInjectionFactoryId(activeFactoryId) ? activeFactoryId : 'huaxing'
})
const factoryName = computed(() => factoryContexts.find((item) => item.id === factoryId.value)?.shortName ?? factoryId.value)
const productionFactories = computed(() => factoryContexts.filter((item) => isInjectionFactoryId(item.id)))

const {
  bootstrap,
  board,
  orders,
  machines,
  molds,
  loading,
  errorMessage,
  viewMode,
  filters,
  visibleLines,
  hasData,
  refresh,
  clearFilters,
} = useInjectionScheduleWorkspace(factoryId)

const savedViews = ref<InjectionScheduleSavedView[]>([])
const viewName = ref('')
const toolsBusy = ref(false)
const toolsMessage = ref('')
interface MoveDraft {
  nonce: number
  lineId: string
  machineId: string
  startAt: string
  finishAt: string
  reason: string
}

const moveDraft = ref<MoveDraft | null>(null)

function draftTimelineMove(payload: Omit<MoveDraft, 'nonce'>) {
  moveDraft.value = { ...payload, nonce: Date.now() }
}

async function loadSavedViews() {
  try {
    savedViews.value = await injectionSchedulingApi.savedViews(factoryId.value)
  } catch (error) {
    toolsMessage.value = getApiErrorMessage(error)
  }
}

async function saveCurrentView() {
  if (!viewName.value.trim()) {
    toolsMessage.value = '请先填写视图名称。'
    return
  }
  toolsBusy.value = true
  toolsMessage.value = ''
  try {
    await injectionSchedulingApi.createSavedView(factoryId.value, viewName.value.trim(), {
      view_mode: viewMode.value,
      columns: [],
      filters: { ...filters },
    })
    viewName.value = ''
    toolsMessage.value = '当前筛选已保存为个人视图。'
    await loadSavedViews()
  } catch (error) {
    toolsMessage.value = getApiErrorMessage(error)
  } finally {
    toolsBusy.value = false
  }
}

function applySavedView(event: Event) {
  const selected = savedViews.value.find(item => item.id === (event.target as HTMLSelectElement).value)
  if (!selected) return
  viewMode.value = selected.config.view_mode ?? 'table'
  Object.assign(filters, selected.config.filters ?? {})
  void refresh()
}

async function exportCurrentTable() {
  toolsBusy.value = true
  toolsMessage.value = ''
  try {
    const blob = await injectionSchedulingApi.exportTable(factoryId.value, filters)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `注塑排产台账-${factoryId.value}.xlsx`
    link.click()
    URL.revokeObjectURL(url)
    toolsMessage.value = '已按当前搜索、状态和优先级导出。'
  } catch (error) {
    toolsMessage.value = getApiErrorMessage(error)
  } finally {
    toolsBusy.value = false
  }
}

async function selectFactory(event: Event) {
  const selected = (event.target as HTMLSelectElement).value as ProductionFactoryContextId
  await router.replace({ query: { ...route.query, factory: selected } })
}

watch([factoryId, () => route.query.factory], ([value, requested]) => {
  const requestedFactoryId = Array.isArray(requested) ? requested[0] : requested
  if (requestedFactoryId !== value) {
    void router.replace({ query: { ...route.query, factory: value } })
    return
  }
  appStore.setActiveFactory(value as ProductionFactoryContextId)
  void loadSavedViews()
}, { immediate: true })
</script>

<template>
  <div class="min-h-screen bg-[linear-gradient(180deg,#f7fbfb_0%,#edf4f6_100%)] px-4 py-4 text-slate-950 sm:px-6">
    <main class="mx-auto w-full max-w-[1920px] space-y-4">
      <header class="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200/80 bg-white/90 px-4 py-3 shadow-sm">
        <div class="flex items-center gap-3">
          <Button as-child variant="ghost" size="sm">
            <RouterLink :to="{ path: '/modules/production', query: { factory: factoryId } }">
              <ArrowLeft aria-hidden="true" />
              生产模块中心
            </RouterLink>
          </Button>
          <div class="h-8 w-px bg-slate-200" />
          <div>
            <div class="flex items-center gap-2">
              <h1 class="text-lg font-bold">注塑排产中枢</h1>
              <span class="rounded-full bg-teal-50 px-2 py-0.5 text-[11px] font-semibold text-teal-700">本地验收 · 未上线</span>
            </div>
            <p class="text-xs text-slate-500">统一计划表 · 机台按厂区 · 模具四厂共享 · {{ factoryName }}</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <label class="text-xs font-medium text-slate-500" for="injection-factory">实体厂区</label>
          <select
            id="injection-factory"
            :value="factoryId"
            class="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold outline-none focus:border-teal-500"
            @change="selectFactory"
          >
            <option v-for="factory in productionFactories" :key="factory.id" :value="factory.id">{{ factory.shortName }}</option>
          </select>
        </div>
      </header>

      <InjectionScheduleKpis :kpis="board?.kpis" />

      <InjectionScheduleImportPanel
        :factory-id="factoryId"
        :profiles="bootstrap?.supported_import_profiles ?? []"
        :can-edit="bootstrap?.capabilities.can_edit ?? false"
        @committed="refresh"
      />

      <InjectionScheduleOperationsPanel
        :factory-id="factoryId"
        :lines="board?.lines ?? []"
        :machines="machines"
        :schedule-revision="board?.schedule_revision ?? 1"
        :start-date="filters.startDate"
        :end-date="filters.endDate"
        :can-edit="bootstrap?.capabilities.can_edit ?? false"
        :can-schedule="bootstrap?.capabilities.can_schedule ?? false"
        :move-draft="moveDraft"
        @changed="refresh"
      />

      <section class="rounded-xl border border-slate-200/80 bg-white/90 p-3 shadow-sm">
        <div class="flex flex-wrap items-center gap-2">
          <Button :variant="viewMode === 'table' ? 'default' : 'ghost'" size="sm" @click="viewMode = 'table'">
            <ListTree aria-hidden="true" />计划表
          </Button>
          <Button :variant="viewMode === 'board' ? 'default' : 'ghost'" size="sm" @click="viewMode = 'board'">
            <Columns3 aria-hidden="true" />机台看板
          </Button>
          <div class="mx-1 h-7 w-px bg-slate-200" />
          <span class="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-3 py-2 text-xs font-medium text-slate-600">
            <ShieldCheck class="size-3.5" aria-hidden="true" />机台按厂区隔离 · 模具公司共享
          </span>
          <span class="ml-auto text-xs text-slate-500">机台 {{ machines.length }} · 模具 {{ molds.length }} · revision {{ board?.schedule_revision ?? 1 }}</span>
        </div>
        <div class="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
          <select class="h-9 min-w-48 rounded-lg border border-slate-200 bg-white px-3 text-sm" @change="applySavedView">
            <option value="">应用保存视图</option>
            <option v-for="item in savedViews" :key="item.id" :value="item.id">{{ item.name }}{{ item.scope === 'FACTORY_SHARED' ? ' · 厂区共享' : '' }}</option>
          </select>
          <input v-model="viewName" class="h-9 w-48 rounded-lg border border-slate-200 px-3 text-sm" maxlength="128" placeholder="个人视图名称">
          <Button variant="outline" size="sm" :disabled="toolsBusy" @click="saveCurrentView"><Save aria-hidden="true" />保存当前视图</Button>
          <Button class="ml-auto" variant="outline" size="sm" :disabled="toolsBusy" @click="exportCurrentTable"><Download aria-hidden="true" />导出当前筛选</Button>
          <p v-if="toolsMessage" class="w-full text-xs text-slate-600">{{ toolsMessage }}</p>
        </div>
      </section>

      <section class="rounded-xl border border-slate-200/80 bg-white/90 p-3 shadow-sm">
        <form class="grid gap-2 lg:grid-cols-[minmax(240px,1fr)_150px_140px_150px_150px_auto]" @submit.prevent="refresh">
          <label class="relative">
            <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <input v-model="filters.search" class="h-10 w-full rounded-lg border border-slate-200 pl-9 pr-3 text-sm outline-none focus:border-teal-500" placeholder="搜索机号、工模、单号、货号或名称">
          </label>
          <select v-model="filters.status" class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500">
            <option value="">全部状态</option>
            <option value="PENDING">待排</option>
            <option value="SCHEDULED">已排</option>
            <option value="IN_PRODUCTION">生产中</option>
            <option value="COMPLETED">已完成</option>
          </select>
          <select v-model="filters.priority" class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500">
            <option value="">全部优先级</option>
            <option value="EXPEDITE">特急</option>
            <option value="URGENT">急单</option>
            <option value="NORMAL">正常</option>
          </select>
          <label class="relative"><CalendarRange class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" /><input v-model="filters.startDate" type="date" class="h-10 w-full rounded-lg border border-slate-200 pl-9 pr-2 text-sm"></label>
          <label class="relative"><CalendarRange class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" /><input v-model="filters.endDate" type="date" class="h-10 w-full rounded-lg border border-slate-200 pl-9 pr-2 text-sm"></label>
          <div class="flex gap-2">
            <Button type="submit" :disabled="loading"><Filter aria-hidden="true" />筛选</Button>
            <Button type="button" variant="ghost" :disabled="loading" @click="clearFilters">清除</Button>
          </div>
        </form>
      </section>

      <section v-if="errorMessage" class="rounded-xl border border-red-200 bg-red-50 px-5 py-6 text-center">
        <p class="font-semibold text-red-800">排产数据读取失败</p>
        <p class="mt-1 text-sm text-red-700">{{ errorMessage }}</p>
        <Button class="mt-4" variant="outline" @click="refresh"><RefreshCw aria-hidden="true" />重新读取</Button>
      </section>

      <section v-else-if="loading" class="rounded-xl border border-slate-200 bg-white px-5 py-20 text-center text-sm text-slate-500">
        正在读取 {{ factoryName }} 的注塑排产数据…
      </section>

      <section v-else-if="!hasData" class="rounded-xl border border-dashed border-slate-300 bg-white/80 px-5 py-20 text-center">
        <p class="text-lg font-bold text-slate-800">当前厂区暂无排产数据</p>
        <p class="mt-2 text-sm text-slate-500">可在上方上传 Excel 生成确定性预览；校验无阻塞错误后，需再次确认才会写入订单。</p>
        <p class="mt-4 text-xs text-slate-400">已识别 {{ bootstrap?.supported_import_profiles.length ?? 4 }} 类导入 profile · 不执行公式、不使用模糊 AI 映射</p>
      </section>

      <InjectionScheduleTable v-else-if="viewMode === 'table'" :lines="visibleLines" :orders="orders" />
      <section v-else class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <InjectionScheduleBoard
          :lines="visibleLines"
          :machines="machines"
          :start-date="filters.startDate"
          :end-date="filters.endDate"
          :day-shift-start="bootstrap?.settings.day_shift_start ?? '08:00'"
          :day-shift-end="bootstrap?.settings.day_shift_end ?? '20:00'"
          :night-shift-start="bootstrap?.settings.night_shift_start ?? '20:00'"
          :night-shift-end="bootstrap?.settings.night_shift_end ?? '08:00'"
          :can-edit="bootstrap?.capabilities.can_edit ?? false"
          @draft-move="draftTimelineMove"
        />
      </section>
    </main>
  </div>
</template>

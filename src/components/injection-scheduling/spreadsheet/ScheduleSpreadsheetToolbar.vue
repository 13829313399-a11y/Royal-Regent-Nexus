<script setup lang="ts">
import {
  ChevronsDownUp,
  ChevronsUpDown,
  Columns3,
  Expand,
  ListFilter,
  RotateCcw,
  Rows3,
  Search,
  SlidersHorizontal,
  StretchHorizontal,
  Table2,
} from '@lucide/vue'
import { onBeforeUnmount, ref, watch } from 'vue'
import type {
  ScheduleFieldScheme,
  SchedulingDensity,
  SchedulingFilters,
  SchedulingViewMode,
} from '@/types/injectionScheduling'

const props = defineProps<{
  viewMode: SchedulingViewMode
  density: SchedulingDensity
  fieldScheme: ScheduleFieldScheme
  filters: SchedulingFilters
  backlogCount: number
  columnChooserOpen: boolean
}>()

const emit = defineEmits<{
  'update:viewMode': [value: SchedulingViewMode]
  'update:density': [value: SchedulingDensity]
  'update:fieldScheme': [value: ScheduleFieldScheme]
  'update:filters': [value: SchedulingFilters]
  toggleColumnChooser: []
  expandAll: []
  collapseAll: []
  openBacklog: []
  enterBigScreen: []
}>()

const searchInput = ref<HTMLInputElement | null>(null)
const localSearch = ref(props.filters.search)
const advancedOpen = ref(false)
let searchTimer: ReturnType<typeof window.setTimeout> | undefined

watch(() => props.filters.search, (value) => {
  if (value !== localSearch.value) localSearch.value = value
})

function patchFilters(patch: Partial<SchedulingFilters>) {
  emit('update:filters', { ...props.filters, ...patch })
}

function updateSearch(value: string) {
  localSearch.value = value
  if (searchTimer) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => patchFilters({ search: value }), 180)
}

function resetFilters() {
  localSearch.value = ''
  emit('update:filters', {
    search: '',
    machineClass: 'all',
    state: 'all',
    exceptionsOnly: false,
    incompleteOnly: false,
    idleOnly: false,
    taskScope: 'all',
    deliveryFrom: '',
    deliveryTo: '',
  })
}

function focusSearch() {
  searchInput.value?.focus()
  searchInput.value?.select()
}

defineExpose({ focusSearch })
onBeforeUnmount(() => searchTimer && window.clearTimeout(searchTimer))
</script>

<template>
  <section class="relative flex min-w-0 items-center gap-1.5 border-b border-slate-200 bg-white px-2 py-1 shadow-sm" data-testid="schedule-spreadsheet-toolbar">
    <div class="flex shrink-0 rounded-md bg-slate-100 p-0.5" role="tablist" aria-label="排程视图">
      <button
        v-for="tab in [
          { id: 'spreadsheet', label: '排程表' },
          { id: 'timeline', label: '时间轴' },
        ] as const"
        :key="tab.id"
        type="button"
        role="tab"
        :aria-selected="viewMode === tab.id"
        class="inline-flex h-7 items-center gap-1 rounded px-2 text-[9px] font-black"
        :class="viewMode === tab.id ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500'"
        @click="emit('update:viewMode', tab.id)"
      >
        <Table2 v-if="tab.id === 'spreadsheet'" class="size-3" />
        <StretchHorizontal v-else class="size-3" />
        {{ tab.label }}
      </button>
    </div>

    <label class="flex h-7 min-w-[180px] flex-1 items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 text-slate-400 xl:max-w-[350px]">
      <Search class="size-3 shrink-0" />
      <input
        ref="searchInput"
        :value="localSearch"
        type="search"
        class="min-w-0 flex-1 border-0 bg-transparent text-[9px] text-slate-900 outline-none"
        placeholder="Ctrl+F 搜索机台、工模、单号、货号、材料…"
        aria-label="搜索排程表"
        @input="updateSearch(($event.target as HTMLInputElement).value)"
      >
    </label>

    <select
      :value="filters.machineClass"
      class="h-7 rounded-md border border-slate-200 bg-white px-1.5 text-[9px] font-bold text-slate-700"
      aria-label="筛选机型"
      @change="patchFilters({ machineClass: ($event.target as HTMLSelectElement).value })"
    >
      <option value="all">全部机型</option>
      <option v-for="type in ['4A', '5A', '7A', '10A', '12A', '14A', '18A', '24A', '32A', '50A', '60A', '80A', '104A', '120A']" :key="type" :value="type">{{ type }}</option>
    </select>

    <select
      :value="filters.taskScope"
      class="hidden h-7 rounded-md border border-slate-200 bg-white px-1.5 text-[9px] font-bold text-slate-700 min-[1150px]:block"
      aria-label="筛选任务范围"
      @change="patchFilters({ taskScope: ($event.target as HTMLSelectElement).value as SchedulingFilters['taskScope'] })"
    >
      <option value="all">全部任务</option>
      <option value="current">当前任务</option>
      <option value="future">后续任务</option>
    </select>

    <label class="hidden h-7 items-center gap-1 px-1 text-[9px] font-bold text-slate-600 min-[1050px]:inline-flex">
      <input :checked="filters.exceptionsOnly" type="checkbox" class="size-3 rounded accent-teal-700" @change="patchFilters({ exceptionsOnly: ($event.target as HTMLInputElement).checked })">
      只看异常
    </label>

    <div class="relative">
      <button type="button" class="toolbar-icon" :class="advancedOpen ? 'border-teal-300 bg-teal-50 text-teal-800' : ''" aria-label="高级筛选" @click="advancedOpen = !advancedOpen">
        <SlidersHorizontal class="size-3.5" />
      </button>
      <div v-if="advancedOpen" class="absolute right-0 top-8 z-50 w-72 rounded-lg border border-slate-200 bg-white p-3 shadow-xl">
        <div class="grid grid-cols-2 gap-2 text-[9px]">
          <label class="grid gap-1 font-bold text-slate-600">机台状态
            <select :value="filters.state" class="h-8 rounded border border-slate-200 px-2" @change="patchFilters({ state: ($event.target as HTMLSelectElement).value })">
              <option value="all">全部状态</option><option value="running">生产中</option><option value="risk">交期风险</option><option value="urgent">特急</option><option value="idle">空闲</option><option value="maintenance">保养</option><option value="fault">故障</option>
            </select>
          </label>
          <label class="flex items-end gap-1.5 pb-2 font-bold text-slate-600"><input :checked="filters.incompleteOnly" type="checkbox" class="size-3.5 accent-teal-700" @change="patchFilters({ incompleteOnly: ($event.target as HTMLInputElement).checked })">资料不全</label>
          <label class="grid gap-1 font-bold text-slate-600">交货期起
            <input :value="filters.deliveryFrom" type="date" class="h-8 rounded border border-slate-200 px-2" @change="patchFilters({ deliveryFrom: ($event.target as HTMLInputElement).value })">
          </label>
          <label class="grid gap-1 font-bold text-slate-600">交货期止
            <input :value="filters.deliveryTo" type="date" class="h-8 rounded border border-slate-200 px-2" @change="patchFilters({ deliveryTo: ($event.target as HTMLInputElement).value })">
          </label>
          <label class="col-span-2 flex items-center gap-1.5 font-bold text-slate-600"><input :checked="filters.idleOnly" type="checkbox" class="size-3.5 accent-teal-700" @change="patchFilters({ idleOnly: ($event.target as HTMLInputElement).checked })">只看空闲机台</label>
        </div>
      </div>
    </div>

    <select
      :value="fieldScheme"
      class="h-7 rounded-md border border-slate-200 bg-white px-1.5 text-[9px] font-black text-teal-800"
      aria-label="字段方案"
      @change="emit('update:fieldScheme', ($event.target as HTMLSelectElement).value as ScheduleFieldScheme)"
    >
      <option value="core">核心字段</option>
      <option value="full">完整字段</option>
      <option value="screen">大屏字段</option>
    </select>

    <button type="button" class="toolbar-icon" :class="columnChooserOpen ? 'border-teal-300 bg-teal-50 text-teal-800' : ''" aria-label="选择表格字段" @click="emit('toggleColumnChooser')"><Columns3 class="size-3.5" /></button>
    <button type="button" class="toolbar-icon hidden min-[1250px]:grid" aria-label="展开全部机台" @click="emit('expandAll')"><ChevronsUpDown class="size-3.5" /></button>
    <button type="button" class="toolbar-icon hidden min-[1250px]:grid" aria-label="收起全部机台" @click="emit('collapseAll')"><ChevronsDownUp class="size-3.5" /></button>

    <div class="hidden shrink-0 rounded-md bg-slate-100 p-0.5 min-[1320px]:flex">
      <button v-for="option in [{ id: 'compact', label: '紧凑' }, { id: 'comfortable', label: '舒适' }] as const" :key="option.id" type="button" class="h-6 rounded px-2 text-[8px] font-black" :class="density === option.id ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500'" @click="emit('update:density', option.id)">
        <Rows3 class="mr-0.5 inline size-2.5" />{{ option.label }}
      </button>
    </div>

    <button type="button" class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 px-2 text-[9px] font-black text-slate-700" @click="emit('openBacklog')">
      <ListFilter class="size-3" />待排池 <span class="rounded-full bg-amber-100 px-1 text-[8px] text-amber-800">{{ backlogCount }}</span>
    </button>
    <button type="button" class="toolbar-icon" aria-label="进入已发布大屏" @click="emit('enterBigScreen')"><Expand class="size-3.5" /></button>
    <button type="button" class="toolbar-icon" aria-label="重置筛选" @click="resetFilters"><RotateCcw class="size-3.5" /></button>
  </section>
</template>

<style scoped>
.toolbar-icon {
  display: grid;
  width: 28px;
  height: 28px;
  flex: none;
  place-items: center;
  border: 1px solid rgb(226 232 240);
  border-radius: 6px;
  color: rgb(71 85 105);
}
.toolbar-icon:hover { border-color: rgb(153 246 228); color: rgb(15 118 110); }
</style>

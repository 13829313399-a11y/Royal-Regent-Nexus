<script setup lang="ts">
import {
  Columns3,
  Expand,
  ListFilter,
  RotateCcw,
  Search,
  StretchHorizontal,
} from '@lucide/vue'
import type {
  SchedulingDensity,
  SchedulingFilters,
  SchedulingViewMode,
} from '@/types/injectionScheduling'

const props = defineProps<{
  viewMode: SchedulingViewMode
  density: SchedulingDensity
  filters: SchedulingFilters
  backlogCount: number
}>()

const emit = defineEmits<{
  'update:viewMode': [value: SchedulingViewMode]
  'update:density': [value: SchedulingDensity]
  'update:filters': [value: SchedulingFilters]
  openBacklog: []
  enterBigScreen: []
}>()

function patchFilters(patch: Partial<SchedulingFilters>) {
  emit('update:filters', { ...props.filters, ...patch })
}

function resetFilters() {
  emit('update:filters', { search: '', machineClass: 'all', state: 'all', exceptionsOnly: false })
}
</script>

<template>
  <section class="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white p-1.5 shadow-sm">
    <div class="flex shrink-0 rounded-lg bg-slate-100 p-0.5" role="tablist" aria-label="排程视图">
      <button
        v-for="tab in [
          { id: 'board', label: '机台板' },
          { id: 'timeline', label: '时间轴' },
        ] as const"
        :key="tab.id"
        type="button"
        role="tab"
        :aria-selected="viewMode === tab.id"
        class="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[10px] font-black transition"
        :class="viewMode === tab.id ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500'"
        @click="emit('update:viewMode', tab.id)"
      >
        <Columns3 v-if="tab.id === 'board'" class="size-3" aria-hidden="true" />
        <StretchHorizontal v-else class="size-3" aria-hidden="true" />
        {{ tab.label }}
      </button>
    </div>

    <label class="flex h-8 min-w-[180px] flex-1 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-slate-400 xl:max-w-[360px]">
      <Search class="size-3.5 shrink-0" aria-hidden="true" />
      <input
        :value="filters.search"
        type="search"
        class="min-w-0 flex-1 border-0 bg-transparent text-[10px] text-slate-900 outline-none"
        placeholder="搜索机台、工模、单号、产品…"
        aria-label="搜索排程"
        @input="patchFilters({ search: ($event.target as HTMLInputElement).value })"
      >
    </label>

    <select
      :value="filters.machineClass"
      class="h-8 rounded-lg border border-slate-200 bg-white px-2 text-[10px] font-bold text-slate-700"
      aria-label="筛选机型"
      @change="patchFilters({ machineClass: ($event.target as HTMLSelectElement).value })"
    >
      <option value="all">全部机型</option>
      <option v-for="type in ['4A', '5A', '7A', '10A', '12A', '14A', '18A', '24A', '32A', '60A', '80A']" :key="type" :value="type">{{ type }}</option>
    </select>

    <select
      :value="filters.state"
      class="hidden h-8 rounded-lg border border-slate-200 bg-white px-2 text-[10px] font-bold text-slate-700 min-[1180px]:block"
      aria-label="筛选状态"
      @change="patchFilters({ state: ($event.target as HTMLSelectElement).value })"
    >
      <option value="all">全部状态</option>
      <option value="running">生产中</option>
      <option value="risk">交期异常</option>
      <option value="urgent">特急任务</option>
      <option value="idle">空闲</option>
      <option value="maintenance">保养</option>
      <option value="fault">机故</option>
    </select>

    <label class="hidden h-8 items-center gap-1.5 px-1 text-[10px] font-bold text-slate-600 min-[1080px]:inline-flex">
      <input
        :checked="filters.exceptionsOnly"
        type="checkbox"
        class="size-3.5 rounded border-slate-300 accent-teal-700"
        @change="patchFilters({ exceptionsOnly: ($event.target as HTMLInputElement).checked })"
      >
      只看异常
    </label>

    <div class="ml-auto hidden shrink-0 rounded-lg bg-slate-100 p-0.5 min-[1250px]:flex">
      <button
        v-for="option in [
          { id: 'compact', label: '紧凑' },
          { id: 'comfortable', label: '舒适' },
        ] as const"
        :key="option.id"
        type="button"
        class="h-7 rounded-md px-2.5 text-[9px] font-black"
        :class="density === option.id ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500'"
        @click="emit('update:density', option.id)"
      >{{ option.label }}</button>
    </div>

    <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-[10px] font-black text-slate-700" @click="emit('openBacklog')">
      <ListFilter class="size-3" />待排池
      <span class="rounded-full bg-amber-100 px-1.5 text-[8px] text-amber-800">{{ backlogCount }}</span>
    </button>
    <button type="button" class="grid size-8 place-items-center rounded-lg border border-slate-200 text-slate-600" aria-label="进入大屏模式" @click="emit('enterBigScreen')"><Expand class="size-3.5" /></button>
    <button type="button" class="grid size-8 place-items-center rounded-lg border border-slate-200 text-slate-600" aria-label="重置筛选" @click="resetFilters"><RotateCcw class="size-3.5" /></button>
  </section>
</template>

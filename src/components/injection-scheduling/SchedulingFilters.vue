<script setup lang="ts">
import { Columns3, ListFilter, Search, StretchHorizontal } from '@lucide/vue'
import type { SchedulingFilters, SchedulingViewMode } from '@/types/injectionScheduling'

const props = defineProps<{
  viewMode: SchedulingViewMode
  filters: SchedulingFilters
  backlogCount: number
  detailsExpanded: boolean
}>()

const emit = defineEmits<{
  'update:viewMode': [value: SchedulingViewMode]
  'update:filters': [value: SchedulingFilters]
  'update:detailsExpanded': [value: boolean]
}>()

function patchFilters(patch: Partial<SchedulingFilters>) {
  emit('update:filters', { ...props.filters, ...patch })
}

const tabs: Array<{ id: SchedulingViewMode; label: string }> = [
  { id: 'board', label: '机台排程板' },
  { id: 'timeline', label: '时间轴总览' },
  { id: 'backlog', label: '待排订单池' },
]
</script>

<template>
  <section class="sticky top-[62px] z-30 rounded-xl border border-slate-200 bg-white/95 p-2.5 shadow-sm backdrop-blur">
    <div class="flex flex-wrap items-center gap-2.5">
      <div class="flex rounded-lg bg-slate-100 p-1" role="tablist" aria-label="排程视图">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          role="tab"
          :aria-selected="viewMode === tab.id"
          class="inline-flex h-9 items-center gap-2 rounded-md px-3 text-xs font-bold transition"
          :class="viewMode === tab.id ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
          @click="emit('update:viewMode', tab.id)"
        >
          <Columns3 v-if="tab.id === 'board'" class="size-3.5" aria-hidden="true" />
          <StretchHorizontal v-else-if="tab.id === 'timeline'" class="size-3.5" aria-hidden="true" />
          <ListFilter v-else class="size-3.5" aria-hidden="true" />
          {{ tab.label }}
          <span v-if="tab.id === 'backlog'" class="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800">
            {{ backlogCount }}
          </span>
        </button>
      </div>

      <label class="flex h-10 min-w-[240px] flex-1 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-slate-400 xl:max-w-sm">
        <Search class="size-4 shrink-0" aria-hidden="true" />
        <input
          :value="filters.search"
          type="search"
          class="min-w-0 flex-1 border-0 bg-transparent text-sm text-slate-900 outline-none"
          placeholder="搜索机台、工模、单号、产品…"
          aria-label="搜索排程"
          @input="patchFilters({ search: ($event.target as HTMLInputElement).value })"
        >
      </label>

      <select
        :value="filters.machineType"
        class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700"
        aria-label="筛选机型"
        @change="patchFilters({ machineType: ($event.target as HTMLSelectElement).value })"
      >
        <option value="all">全部机型</option>
        <option v-for="type in ['5A', '12A', '18A', '32A', '50A']" :key="type" :value="type">{{ type }}</option>
      </select>

      <select
        :value="filters.state"
        class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700"
        aria-label="筛选状态"
        @change="patchFilters({ state: ($event.target as HTMLSelectElement).value })"
      >
        <option value="all">全部状态</option>
        <option value="running">生产中</option>
        <option value="risk">交期异常</option>
        <option value="urgent">特急任务</option>
        <option value="idle">空闲</option>
      </select>

      <label class="inline-flex h-10 items-center gap-2 rounded-lg px-2 text-xs font-semibold text-slate-600">
        <input
          :checked="filters.exceptionsOnly"
          type="checkbox"
          class="size-4 rounded border-slate-300 accent-teal-700"
          @change="patchFilters({ exceptionsOnly: ($event.target as HTMLInputElement).checked })"
        >
        只看异常
      </label>

      <button
        type="button"
        class="h-10 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700 hover:border-teal-200 hover:bg-teal-50"
        @click="emit('update:detailsExpanded', !detailsExpanded)"
      >
        {{ detailsExpanded ? '收起明细' : '展开明细' }}
      </button>
    </div>
  </section>
</template>


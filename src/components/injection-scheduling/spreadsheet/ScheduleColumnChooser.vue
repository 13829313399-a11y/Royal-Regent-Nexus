<script setup lang="ts">
import { Check, LockKeyhole, X } from '@lucide/vue'
import { computed } from 'vue'
import {
  scheduleSpreadsheetColumns,
  type ScheduleSpreadsheetColumnKey,
} from './scheduleSpreadsheetColumns'

const props = defineProps<{
  open: boolean
  hiddenColumns: ScheduleSpreadsheetColumnKey[]
  availableColumns: ScheduleSpreadsheetColumnKey[]
}>()

const emit = defineEmits<{
  close: []
  toggle: [key: ScheduleSpreadsheetColumnKey]
  reset: []
}>()

const groupedColumns = computed(() => {
  const groups = new Map<string, typeof scheduleSpreadsheetColumns>()
  for (const column of scheduleSpreadsheetColumns) {
    const bucket = groups.get(column.group) ?? []
    bucket.push(column)
    groups.set(column.group, bucket)
  }
  return [...groups.entries()]
})

function isVisible(key: ScheduleSpreadsheetColumnKey) {
  return props.availableColumns.includes(key) && !props.hiddenColumns.includes(key)
}

function canToggle(key: ScheduleSpreadsheetColumnKey, sensitive?: boolean) {
  return !sensitive && props.availableColumns.includes(key)
}
</script>

<template>
  <div
    v-if="open"
    class="absolute right-2 top-[42px] z-50 flex max-h-[min(560px,calc(100vh-150px))] w-[360px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl"
    data-testid="schedule-column-chooser"
  >
    <header class="flex h-10 shrink-0 items-center border-b border-slate-200 px-3">
      <div>
        <strong class="block text-[11px] text-slate-900">表格字段</strong>
        <span class="block text-[8px] text-slate-400">按当前字段方案选择可见列</span>
      </div>
      <button type="button" class="ml-auto grid size-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100" aria-label="关闭字段选择" @click="emit('close')">
        <X class="size-3.5" />
      </button>
    </header>

    <div class="min-h-0 overflow-auto p-2 [scrollbar-width:thin]">
      <section v-for="[group, columns] in groupedColumns" :key="group" class="mb-3 last:mb-0">
        <h3 class="mb-1 px-1 text-[8px] font-black uppercase tracking-[0.12em] text-slate-400">{{ group }}</h3>
        <div class="grid grid-cols-2 gap-1">
          <button
            v-for="column in columns"
            :key="column.key"
            type="button"
            class="flex min-h-8 items-center gap-2 rounded-lg border px-2 text-left text-[9px] font-bold"
            :class="!canToggle(column.key, column.sensitive)
              ? 'cursor-not-allowed border-dashed border-slate-200 bg-slate-50 text-slate-400'
              : isVisible(column.key)
                ? 'border-teal-200 bg-teal-50 text-teal-900'
                : 'border-slate-200 bg-white text-slate-500 hover:border-teal-200'"
            :disabled="!canToggle(column.key, column.sensitive)"
            :title="column.sensitive ? '商业字段需要后端权限合同，当前不下发、不展示' : !availableColumns.includes(column.key) ? '请切换字段方案后设置该列' : column.label"
            @click="canToggle(column.key, column.sensitive) && emit('toggle', column.key)"
          >
            <span class="grid size-4 shrink-0 place-items-center rounded" :class="isVisible(column.key) && !column.sensitive ? 'bg-teal-700 text-white' : 'bg-slate-100 text-slate-400'">
              <LockKeyhole v-if="column.sensitive" class="size-2.5" />
              <Check v-else-if="isVisible(column.key)" class="size-2.5" />
            </span>
            <span class="min-w-0 truncate">{{ column.label }}</span>
          </button>
        </div>
      </section>
    </div>

    <footer class="flex shrink-0 items-center justify-between border-t border-slate-200 bg-slate-50 px-3 py-2">
      <span class="text-[8px] text-slate-500">商业字段保持后端隔离</span>
      <button type="button" class="h-7 rounded-md border border-slate-200 bg-white px-2.5 text-[9px] font-black text-slate-600" @click="emit('reset')">恢复默认</button>
    </footer>
  </div>
</template>

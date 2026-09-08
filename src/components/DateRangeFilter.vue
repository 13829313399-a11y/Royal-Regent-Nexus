<script setup lang="ts">
import { ref, shallowRef, watch } from 'vue'
import { CalendarClock } from '@lucide/vue'
import {
  PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent,
  RangeCalendarRoot, RangeCalendarHeader, RangeCalendarHeading, RangeCalendarPrev, RangeCalendarNext,
  RangeCalendarGrid, RangeCalendarGridHead, RangeCalendarGridBody, RangeCalendarGridRow,
  RangeCalendarHeadCell, RangeCalendarCell, RangeCalendarCellTrigger, type DateRange,
} from 'reka-ui'

defineProps<{ label: string }>()
const model = defineModel<DateRange>({ required: true })
const open = ref(false)
const draft = shallowRef<DateRange>({ start: undefined, end: undefined })

function setOpen(value: boolean) {
  draft.value = { start: model.value.start?.copy(), end: model.value.end?.copy() }
  open.value = value
}

function selectRange(value: DateRange | undefined) {
  draft.value = value ?? { start: undefined, end: undefined }
  if (!value?.start || !value.end) return
  model.value = value
  open.value = false
}

function clearRange() {
  model.value = { start: undefined, end: undefined }
  draft.value = { start: undefined, end: undefined }
  open.value = false
}

watch(model, () => { open.value = false })
</script>

<template>
  <PopoverRoot :open="open" @update:open="setOpen">
    <PopoverTrigger as-child><button type="button" :aria-label="label" class="inline-flex h-9 min-w-52 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 hover:border-teal-400"><span>{{ model.start && model.end ? `${model.start} 至 ${model.end}` : '选择日期范围' }}</span><CalendarClock class="size-4 text-slate-400" /></button></PopoverTrigger>
    <PopoverPortal>
      <PopoverContent align="start" :side-offset="8" :collision-padding="12" class="z-[80] max-h-[min(80vh,var(--reka-popover-content-available-height))] w-[min(600px,calc(100vw-2rem))] overflow-auto rounded-xl border border-slate-200 bg-white p-4 shadow-xl" data-testid="date-range-calendar">
        <p role="status" class="mb-3 text-sm font-semibold text-teal-800">{{ draft.start && !draft.end ? '请选择结束日期' : '请选择开始日期，再选择结束日期' }}</p>
        <RangeCalendarRoot v-slot="{ grid, weekDays }" :model-value="draft" :calendar-label="label" locale="zh-CN" :week-starts-on="1" :number-of-months="2" prevent-deselect fixed-weeks initial-focus @update:model-value="selectRange">
          <RangeCalendarHeader class="mb-3 flex items-center justify-between">
            <RangeCalendarPrev aria-label="上个月" class="flex size-8 items-center justify-center rounded-lg border border-slate-200 text-lg hover:bg-slate-50">‹</RangeCalendarPrev>
            <RangeCalendarHeading class="text-sm font-bold text-slate-900" />
            <RangeCalendarNext aria-label="下个月" class="flex size-8 items-center justify-center rounded-lg border border-slate-200 text-lg hover:bg-slate-50">›</RangeCalendarNext>
          </RangeCalendarHeader>
          <div class="grid gap-4 sm:grid-cols-2">
            <RangeCalendarGrid v-for="month in grid" :key="month.value.toString()" class="w-full table-fixed border-collapse text-center text-sm">
              <caption class="pb-2 text-xs font-semibold text-slate-500">{{ month.value.year }} 年 {{ month.value.month }} 月</caption>
              <RangeCalendarGridHead><RangeCalendarGridRow><RangeCalendarHeadCell v-for="day in weekDays" :key="day" class="h-8 text-xs font-medium text-slate-400">{{ day }}</RangeCalendarHeadCell></RangeCalendarGridRow></RangeCalendarGridHead>
              <RangeCalendarGridBody><RangeCalendarGridRow v-for="(week, index) in month.rows" :key="index"><RangeCalendarCell v-for="day in week" :key="day.toString()" :date="day" class="p-0.5"><RangeCalendarCellTrigger :day="day" :month="month.value" class="inline-flex h-9 w-full items-center justify-center rounded-md text-sm text-slate-700 outline-none hover:bg-teal-50 focus-visible:ring-2 focus-visible:ring-teal-500 data-[outside-view]:invisible data-[selected]:bg-teal-100 data-[highlighted]:bg-teal-50 data-[selection-start]:bg-teal-700 data-[selection-start]:text-white data-[selection-end]:bg-teal-700 data-[selection-end]:text-white data-[today]:font-bold" /></RangeCalendarCell></RangeCalendarGridRow></RangeCalendarGridBody>
            </RangeCalendarGrid>
          </div>
        </RangeCalendarRoot>
        <div class="mt-3 flex items-center justify-between border-t border-slate-100 pt-3"><span class="text-xs text-slate-500">连续点击两天即可，可跨月选择</span><button type="button" class="text-xs font-semibold text-teal-700" @click="clearRange">清除日期</button></div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>

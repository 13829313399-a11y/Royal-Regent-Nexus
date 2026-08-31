<script setup lang="ts">
import { computed, ref } from 'vue'
import type { InjectionScheduleLine, InjectionScheduleMachine } from '@/types/injectionScheduling'

const props = defineProps<{
  lines: InjectionScheduleLine[]
  machines: InjectionScheduleMachine[]
  startDate: string
  endDate: string
  dayShiftStart: string
  dayShiftEnd: string
  nightShiftStart: string
  nightShiftEnd: string
  canEdit: boolean
}>()

const emit = defineEmits<{
  draftMove: [payload: {
    lineId: string
    machineId: string
    startAt: string
    finishAt: string
    reason: string
  }]
}>()

interface ShiftSlot {
  key: string
  date: string
  dateLabel: string
  shift: 'DAY' | 'NIGHT'
  shiftLabel: string
  startAt: string
  finishAt: string
}

const selectedLineId = ref('')
const draggingLineId = ref('')
const boardMessage = ref('')

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function localDate(value: Date) {
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

function localDateTime(value: Date) {
  return `${localDate(value)}T${pad(value.getHours())}:${pad(value.getMinutes())}`
}

function shiftRange(date: string, startTime: string, endTime: string) {
  const start = new Date(`${date}T${startTime}:00`)
  const finish = new Date(`${date}T${endTime}:00`)
  if (finish <= start) finish.setDate(finish.getDate() + 1)
  return { startAt: localDateTime(start), finishAt: localDateTime(finish) }
}

const slots = computed<ShiftSlot[]>(() => {
  const start = new Date(`${props.startDate}T00:00:00`)
  const finish = new Date(`${props.endDate}T00:00:00`)
  if (Number.isNaN(start.getTime()) || Number.isNaN(finish.getTime()) || start > finish) return []
  const values: ShiftSlot[] = []
  const cursor = new Date(start)
  let days = 0
  while (cursor <= finish && days < 31) {
    const date = localDate(cursor)
    const day = shiftRange(date, props.dayShiftStart, props.dayShiftEnd)
    const night = shiftRange(date, props.nightShiftStart, props.nightShiftEnd)
    values.push(
      { key: `${date}:DAY`, date, dateLabel: `${cursor.getMonth() + 1}/${cursor.getDate()}`, shift: 'DAY', shiftLabel: '白班', ...day },
      { key: `${date}:NIGHT`, date, dateLabel: `${cursor.getMonth() + 1}/${cursor.getDate()}`, shift: 'NIGHT', shiftLabel: '夜班', ...night },
    )
    cursor.setDate(cursor.getDate() + 1)
    days += 1
  }
  return values
})

const linesBySlot = computed(() => {
  const result = new Map<string, InjectionScheduleLine[]>()
  for (const line of props.lines) {
    if (!line.machine_id || !line.planned_start_at) continue
    const date = line.planned_start_at.slice(0, 10)
    const time = line.planned_start_at.slice(11, 16)
    const shift = time >= props.nightShiftStart || time < props.dayShiftStart ? 'NIGHT' : 'DAY'
    const key = `${line.machine_id}:${date}:${shift}`
    result.set(key, [...(result.get(key) ?? []), line])
  }
  return result
})

const unassigned = computed(() => props.lines.filter(line => !line.machine_id))
const selectedLine = computed(() => props.lines.find(line => line.id === selectedLineId.value) ?? null)
const gridStyle = computed(() => ({
  gridTemplateColumns: `180px repeat(${slots.value.length}, minmax(150px, 1fr))`,
  minWidth: `${180 + slots.value.length * 150}px`,
}))

function slotLines(machineId: string, slot: ShiftSlot) {
  return linesBySlot.value.get(`${machineId}:${slot.key}`) ?? []
}

function startDrag(event: DragEvent, line: InjectionScheduleLine) {
  if (!props.canEdit || line.is_locked || !event.dataTransfer) return
  draggingLineId.value = line.id
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', line.id)
  selectedLineId.value = line.id
}

function dropOnSlot(event: DragEvent, machineId: string, slot: ShiftSlot) {
  const lineId = event.dataTransfer?.getData('text/plain') || draggingLineId.value
  const line = props.lines.find(item => item.id === lineId)
  if (!props.canEdit || !line || line.is_locked) return
  emit('draftMove', {
    lineId,
    machineId,
    startAt: slot.startAt,
    finishAt: slot.finishAt,
    reason: `时间轴拖放至 ${slot.dateLabel} ${slot.shiftLabel}`,
  })
  draggingLineId.value = ''
  boardMessage.value = '移动草案已填入上方操作区；请先校验，再确认写入。'
}
</script>

<template>
  <div class="space-y-3">
    <section class="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div><h3 class="font-bold text-slate-900">待排订单池</h3><p class="text-xs text-slate-500">拖到机台的白班/夜班格只会生成草案，不会直接写库。</p></div>
        <span class="rounded-full bg-white px-2 py-1 text-xs font-semibold text-slate-600">{{ unassigned.length }} 条</span>
      </div>
      <div class="mt-3 flex gap-2 overflow-x-auto pb-1">
        <button
          v-for="line in unassigned"
          :key="line.id"
          type="button"
          :draggable="canEdit && !line.is_locked"
          class="min-w-52 rounded-lg border border-slate-200 bg-white p-3 text-left shadow-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
          @click="selectedLineId = line.id"
          @dragstart="startDrag($event, line)"
          @dragend="draggingLineId = ''"
        >
          <span class="text-xs font-semibold text-teal-700">{{ line.priority }}</span>
          <strong class="mt-1 block text-sm text-slate-900">{{ line.product_code }}</strong>
          <span class="mt-1 block truncate text-xs text-slate-500">{{ line.order_no }} · {{ line.mold_code }}</span>
        </button>
        <p v-if="!unassigned.length" class="py-4 text-sm text-slate-400">当前筛选范围没有待排订单。</p>
      </div>
    </section>

    <p v-if="boardMessage" class="rounded-lg bg-teal-50 px-3 py-2 text-xs font-medium text-teal-800">{{ boardMessage }}</p>

    <div class="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <div role="grid" aria-label="注塑机台班次时间轴" class="grid" :style="gridStyle">
        <div class="sticky left-0 z-20 border-b border-r border-slate-200 bg-slate-100 p-3 text-xs font-bold text-slate-600">机台固定栏</div>
        <div v-for="slot in slots" :key="`header:${slot.key}`" role="columnheader" class="border-b border-r border-slate-200 bg-slate-100 px-2 py-2 text-center">
          <p class="text-xs font-bold text-slate-700">{{ slot.dateLabel }}</p>
          <p class="text-[11px]" :class="slot.shift === 'DAY' ? 'text-amber-700' : 'text-indigo-700'">{{ slot.shiftLabel }}</p>
        </div>

        <template v-for="machine in machines" :key="machine.id">
          <div role="rowheader" class="sticky left-0 z-10 border-b border-r border-slate-200 bg-white p-3">
            <p class="font-bold text-slate-900">{{ machine.machine_code }}</p>
            <p class="mt-1 text-xs text-slate-500">{{ [machine.machine_a_label, machine.robot_arm_type].filter(Boolean).join(' · ') || '能力待补齐' }}</p>
            <p class="mt-1 text-[11px]" :class="machine.status === 'AVAILABLE' ? 'text-emerald-700' : 'text-amber-700'">{{ machine.status }}</p>
          </div>
          <div
            v-for="slot in slots"
            :key="`${machine.id}:${slot.key}`"
            role="gridcell"
            :aria-label="`${machine.machine_code} ${slot.dateLabel} ${slot.shiftLabel} 排程格`"
            class="min-h-28 border-b border-r border-slate-200 p-1.5 transition-colors hover:bg-teal-50/50"
            @dragenter.prevent
            @dragover.prevent
            @drop.prevent="dropOnSlot($event, machine.id, slot)"
          >
            <button
              v-for="line in slotLines(machine.id, slot)"
              :key="line.id"
              type="button"
              :draggable="canEdit && !line.is_locked"
              class="mb-1.5 block w-full rounded-md border p-2 text-left shadow-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
              :class="line.is_locked ? 'border-slate-300 bg-slate-100' : line.priority === 'EXPEDITE' ? 'border-red-200 bg-red-50' : 'border-teal-200 bg-teal-50'"
              @click="selectedLineId = line.id"
              @dragstart="startDrag($event, line)"
              @dragend="draggingLineId = ''"
            >
              <span class="flex items-center justify-between gap-1 text-[11px]"><strong class="truncate text-slate-900">{{ line.product_code }}</strong><span>{{ line.completion_percent }}%</span></span>
              <span class="mt-1 block truncate text-[10px] text-slate-600">{{ line.mold_code }} · 欠 {{ line.remaining_shots }}</span>
              <span v-if="line.is_locked" class="mt-1 block text-[10px] font-semibold text-slate-500">已锁定</span>
            </button>
          </div>
        </template>
      </div>
    </div>

    <aside v-if="selectedLine" class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div><p class="text-xs font-semibold text-teal-700">订单详情</p><h3 class="mt-1 font-bold text-slate-950">{{ selectedLine.order_no }} · {{ selectedLine.product_code }}</h3><p class="text-sm text-slate-500">{{ selectedLine.product_name || selectedLine.mold_code }}</p></div>
        <button type="button" class="text-xs text-slate-500 hover:text-slate-900" @click="selectedLineId = ''">关闭</button>
      </div>
      <dl class="mt-4 grid gap-3 text-xs sm:grid-cols-3 lg:grid-cols-6">
        <div><dt class="text-slate-400">机台</dt><dd class="mt-1 font-semibold">{{ selectedLine.machine_code || '未排' }}</dd></div>
        <div><dt class="text-slate-400">状态</dt><dd class="mt-1 font-semibold">{{ selectedLine.status }}</dd></div>
        <div><dt class="text-slate-400">计划开始</dt><dd class="mt-1 font-semibold">{{ selectedLine.planned_start_at || '—' }}</dd></div>
        <div><dt class="text-slate-400">计划完成</dt><dd class="mt-1 font-semibold">{{ selectedLine.planned_finish_at || '—' }}</dd></div>
        <div><dt class="text-slate-400">已啤 / 欠数</dt><dd class="mt-1 font-semibold">{{ selectedLine.qualified_shots }} / {{ selectedLine.remaining_shots }}</dd></div>
        <div><dt class="text-slate-400">进度</dt><dd class="mt-1 font-semibold">{{ selectedLine.completion_percent }}%</dd></div>
      </dl>
    </aside>
  </div>
</template>

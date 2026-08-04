<script setup lang="ts">
import { computed } from 'vue'
import { CalendarRange } from '@lucide/vue'
import type { MachineRecord, OrderRecord, ScheduleTaskRecord } from '../types'

const props = defineProps<{ machines: MachineRecord[]; tasks: ScheduleTaskRecord[]; orders: OrderRecord[] }>()
const orderMap = computed(() => new Map(props.orders.map((item) => [item.id, item])))
const nowOffset = computed(() => {
  const today = new Date()
  const start = new Date(2026, 7, 4)
  const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const day = Math.floor((todayStart.getTime() - start.getTime()) / 86_400_000)
  return day >= 0 && day <= 7 ? day * 12.5 : null
})
function width(task: ScheduleTaskRecord) { const start = Date.parse(task.plannedStart.replace(' ', 'T')); const finish = Date.parse(task.plannedFinish.replace(' ', 'T')); return Number.isFinite(finish - start) ? Math.max(8, Math.min(42, (finish - start) / 86_400_000 * 12)) : 14 }
function offset(task: ScheduleTaskRecord) { const day = Number(task.plannedStart.slice(8, 10)) || 4; return Math.max(0, Math.min(78, (day - 4) * 12)) }
function overdue(task: ScheduleTaskRecord) { return (orderMap.value.get(task.orderId)?.deliverySlackDays ?? 0) < 0 }
</script>

<template>
  <section class="timeline-view"><header><div><CalendarRange :size="18" /><strong>机台时间轴</strong><span>2026-08-04 — 2026-08-11</span></div><p>只读时间轴 · 当前任务固定在最前</p></header><div class="timeline-scale"><span v-for="day in 8" :key="day">08-{{ String(day + 3).padStart(2, '0') }}</span></div><div class="timeline-rows"><article v-for="machine in machines" :key="machine.id"><div class="timeline-machine"><strong>{{ machine.code }}</strong><span>{{ machine.aClass ?? '—' }}A · {{ machine.injectionCapacityG ?? '—' }}g</span></div><div class="timeline-track"><i v-if="nowOffset !== null" class="timeline-now" :style="{ left: `${nowOffset}%` }"><span>现在</span></i><button v-for="task in tasks.filter((item) => item.machineId === machine.id)" :key="task.id" :class="[task.status.toLowerCase(), { overdue: overdue(task) }]" :style="{ left: `${offset(task)}%`, width: `${width(task)}%` }" :title="`${orderMap.get(task.orderId)?.orderNo ?? ''} · ${orderMap.get(task.orderId)?.productName ?? ''} · ${task.plannedStart} - ${task.plannedFinish}`"><b>{{ orderMap.get(task.orderId)?.orderNo ?? task.id }}</b><span>{{ orderMap.get(task.orderId)?.productName }}</span></button></div></article></div></section>
</template>

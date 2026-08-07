<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { AlertTriangle, CalendarRange, Minus, Plus } from '@lucide/vue'
import type { MachineRecord, OrderRecord, ScheduleTaskRecord } from '../types'

const props = defineProps<{ machines: MachineRecord[]; tasks: ScheduleTaskRecord[]; orders: OrderRecord[]; businessDate: string; scrollLeft: number; zoom: number }>()
const emit = defineEmits<{ 'update:scrollLeft': [value: number]; 'update:zoom': [value: number] }>()
const scroller = ref<HTMLElement | null>(null)
const dayMs = 86_400_000
const orderMap = computed(() => new Map(props.orders.map((item) => [item.id, item])))

function localWallClock(value: string) {
  const text = value.trim().replace(' ', 'T')
  const local = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(text)
  if (local) return Date.UTC(Number(local[1]), Number(local[2]) - 1, Number(local[3]), Number(local[4]), Number(local[5]), Number(local[6] ?? 0))
  const instant = Date.parse(text)
  return Number.isFinite(instant) ? instant + 8 * 3_600_000 : Number.NaN
}
function businessDayStart(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  return match ? Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : Date.now() + 8 * 3_600_000
}
const parsedTasks = computed(() => props.tasks.map((task) => ({ task, start: localWallClock(task.plannedStart), finish: localWallClock(task.plannedFinish) })))
const invalidTasks = computed(() => parsedTasks.value.filter((item) => !Number.isFinite(item.start) || !Number.isFinite(item.finish) || item.finish <= item.start))
const validTasks = computed(() => parsedTasks.value.filter((item) => Number.isFinite(item.start) && Number.isFinite(item.finish) && item.finish > item.start))
const range = computed(() => {
  const businessStart = businessDayStart(props.businessDate)
  const earliest = validTasks.value.length ? Math.min(...validTasks.value.map((item) => item.start)) : businessStart
  const start = Math.min(businessStart, earliest)
  const latest = validTasks.value.length ? Math.max(...validTasks.value.map((item) => item.finish)) : start
  const end = Math.max(start + 14 * dayMs, latest)
  return { start, end, duration: end - start, days: Math.ceil((end - start) / dayMs) }
})
const ticks = computed(() => {
  const step = Math.max(1, Math.ceil(range.value.days / 14))
  const values: Array<{ at: number; label: string }> = []
  for (let at = range.value.start; at <= range.value.end; at += step * dayMs) values.push({ at, label: formatDate(at) })
  return values
})
const trackWidth = computed(() => `${Math.max(100, range.value.days * 68 * props.zoom)}px`)
const nowOffset = computed(() => {
  const now = Date.now() + 8 * 3_600_000
  return now >= range.value.start && now <= range.value.end ? (now - range.value.start) / range.value.duration * 100 : null
})
function formatDate(value: number) { return new Date(value).toISOString().slice(0, 10) }
function offset(start: number) { return Math.max(0, Math.min(100, (start - range.value.start) / range.value.duration * 100)) }
function width(start: number, finish: number) { return Math.max(.35, Math.min(100, (finish - start) / range.value.duration * 100)) }
function overdue(task: ScheduleTaskRecord) { return (orderMap.value.get(task.orderId)?.deliverySlackDays ?? 0) < 0 }
async function restoreScroll() { await nextTick(); if (scroller.value) scroller.value.scrollLeft = props.scrollLeft }
watch(() => [props.scrollLeft, props.businessDate] as const, restoreScroll)
onMounted(restoreScroll)
</script>

<template>
  <section class="timeline-view">
    <header><div><CalendarRange :size="18" /><strong>机台时间轴</strong><span>{{ formatDate(range.start) }} — {{ formatDate(range.end) }} · Asia/Shanghai</span></div><p>只读时间轴 · 当前计划切片 <button aria-label="缩小时间轴" @click="emit('update:zoom', zoom - .25)"><Minus :size="13" /></button><b>{{ Math.round(zoom * 100) }}%</b><button aria-label="放大时间轴" @click="emit('update:zoom', zoom + .25)"><Plus :size="13" /></button></p></header>
    <p v-if="invalidTasks.length" class="timeline-warning"><AlertTriangle :size="15" />{{ invalidTasks.length }} 个任务的计划起止无效，已从范围计算中排除；请在问题列表中修正。</p>
    <div ref="scroller" class="timeline-scroll" @scroll="emit('update:scrollLeft', ($event.currentTarget as HTMLElement).scrollLeft)">
      <div class="timeline-canvas" :style="{ width: trackWidth }">
        <div class="timeline-scale"><span v-for="tick in ticks" :key="tick.at" :style="{ left: `${offset(tick.at)}%` }">{{ tick.label }}</span></div>
        <div class="timeline-rows"><article v-for="machine in machines" :key="machine.id"><div class="timeline-machine"><strong>{{ machine.code }}</strong><span>{{ machine.aClass ?? '—' }}A · {{ machine.injectionCapacityG ?? '—' }}g</span></div><div class="timeline-track"><i v-if="nowOffset !== null" class="timeline-now" :style="{ left: `${nowOffset}%` }"><span>现在</span></i><button v-for="item in validTasks.filter((entry) => entry.task.machineId === machine.id)" :key="item.task.id" :class="[item.task.status.toLowerCase(), { overdue: overdue(item.task) }]" :style="{ left: `${offset(item.start)}%`, width: `${width(item.start, item.finish)}%` }" :title="`${orderMap.get(item.task.orderId)?.orderNo ?? ''} · ${orderMap.get(item.task.orderId)?.productName ?? ''} · ${item.task.plannedStart} - ${item.task.plannedFinish}`"><b>{{ orderMap.get(item.task.orderId)?.orderNo ?? item.task.id }}</b><span>{{ orderMap.get(item.task.orderId)?.productName }}</span></button></div></article></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.timeline-scroll{overflow:auto}.timeline-canvas{min-width:100%}.timeline-scale{position:relative;height:32px}.timeline-scale span{position:absolute;transform:translateX(-50%);white-space:nowrap}.timeline-warning{display:flex;gap:7px;align-items:center;margin:8px 14px;padding:8px 10px;border-radius:8px;background:#fff7ed;color:#9a3412;font-size:12px}.timeline-machine{position:sticky;left:0;z-index:2}.timeline-view header p{display:flex;align-items:center;gap:5px}.timeline-view header p button{display:grid;place-items:center;border:1px solid #cbd5e1;border-radius:6px;background:#fff;padding:3px}
</style>

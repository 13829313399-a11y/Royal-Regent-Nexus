<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, CheckCircle2, PackageCheck, Truck } from '@lucide/vue'
import StatusPill from '@/components/common/StatusPill.vue'
import type { ShippingFactoryProfile, VehicleTrip } from './contracts'
import {
  WAREHOUSE_CBM_LIMIT,
  cbmText,
  recommendTruck,
  shipmentModeMeta,
  shipmentStatusMeta,
} from './contracts'

const props = defineProps<{ profile: ShippingFactoryProfile }>()

const warehouseTasks = computed(() => props.profile.tasks.filter((task) => task.vehicles.length > 0))

const summary = computed(() => {
  const trips = warehouseTasks.value.flatMap((task) => task.vehicles)
  return {
    tasks: warehouseTasks.value.length,
    trips: trips.length,
    cbm: trips.reduce((total, trip) => total + trip.cbm, 0),
    overLimit: trips.filter((trip) => trip.cbm > WAREHOUSE_CBM_LIMIT).length,
    missingTruck: trips.filter((trip) => !trip.truckType.trim()).length,
  }
})

function percent(trip: VehicleTrip) {
  return Math.min(100, Math.round((trip.cbm / WAREHOUSE_CBM_LIMIT) * 100))
}

function tone(trip: VehicleTrip) {
  if (trip.cbm > WAREHOUSE_CBM_LIMIT) return 'red' as const
  if (!trip.truckType.trim()) return 'amber' as const
  return 'teal' as const
}

function tripState(trip: VehicleTrip) {
  if (trip.cbm > WAREHOUSE_CBM_LIMIT) return { label: '超出 35 CBM', tone: 'red' as const }
  if (!trip.truckType.trim()) return { label: '吨车待填写', tone: 'amber' as const }
  return { label: '分车合规', tone: 'green' as const }
}
</script>

<template>
  <div class="space-y-4">
    <section class="grid grid-cols-2 gap-3 xl:grid-cols-4" aria-label="分车概览">
      <article class="rounded-xl border border-slate-200 bg-white p-4">
        <p class="text-[11px] font-semibold text-slate-500">交仓任务</p>
        <p class="mt-2 text-3xl font-semibold leading-none text-slate-950 tabular-nums">{{ summary.tasks }}</p>
        <p class="mt-2 text-[11px] text-slate-400">按裕泰仓 35 CBM 口径分车</p>
      </article>
      <article class="rounded-xl border border-slate-200 bg-white p-4">
        <p class="text-[11px] font-semibold text-slate-500">车辆总数</p>
        <p class="mt-2 text-3xl font-semibold leading-none text-slate-950 tabular-nums">{{ summary.trips }}</p>
        <p class="mt-2 text-[11px] text-slate-400">合计 {{ cbmText(summary.cbm) }} CBM</p>
      </article>
      <article class="rounded-xl border border-slate-200 bg-white p-4">
        <p class="text-[11px] font-semibold text-slate-500">超出上限</p>
        <p class="mt-2 text-3xl font-semibold leading-none tabular-nums" :class="summary.overLimit ? 'text-red-600' : 'text-slate-950'">
          {{ summary.overLimit }}
        </p>
        <p class="mt-2 text-[11px] text-slate-400">超限车辆需拆车后重新确认</p>
      </article>
      <article class="rounded-xl border border-slate-200 bg-white p-4">
        <p class="text-[11px] font-semibold text-slate-500">吨车待填写</p>
        <p class="mt-2 text-3xl font-semibold leading-none tabular-nums" :class="summary.missingTruck ? 'text-amber-700' : 'text-slate-950'">
          {{ summary.missingTruck }}
        </p>
        <p class="mt-2 text-[11px] text-slate-400">超过 50 CBM 必须人工指定吨车</p>
      </article>
    </section>

    <section
      v-for="task in warehouseTasks"
      :key="task.id"
      class="enterprise-panel rounded-xl"
      :aria-label="`${task.batchNo} 分车明细`"
    >
      <header class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div class="min-w-0">
          <p class="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
            <StatusPill :label="shipmentStatusMeta[task.status].label" :tone="shipmentStatusMeta[task.status].tone" compact />
            <StatusPill :label="shipmentModeMeta[task.mode].label" :tone="shipmentModeMeta[task.mode].tone" compact />
            <span>{{ task.customer }}</span>
          </p>
          <h2 class="mt-1.5 text-base font-semibold tracking-[-0.02em] text-slate-950">
            <span class="tabular-nums">{{ task.batchNo }}</span> · {{ task.warehouse }} · {{ task.truckType || '吨车待确认' }}
          </h2>
          <p class="mt-1 text-[12px] text-slate-500">
            交仓日期 {{ task.deliveryDate || '待预约' }} · 负责人 {{ task.coordinator }} · SO {{ task.so }}
          </p>
        </div>
        <p class="text-[11px] text-slate-500">{{ task.vehicles.length }} 车</p>
      </header>

      <div class="grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="trip in task.vehicles"
          :key="trip.key"
          class="rounded-xl border border-slate-200 bg-white p-4"
        >
          <div class="flex items-start justify-between gap-2">
            <div>
              <p class="text-[13px] font-bold text-slate-950">{{ trip.key }}</p>
              <p class="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500">
                <Truck class="size-3.5 text-slate-400" aria-hidden="true" />
                {{ trip.truckType || `建议 ${recommendTruck(trip.cbm) || '人工确认'}` }}
              </p>
            </div>
            <StatusPill :label="tripState(trip).label" :tone="tripState(trip).tone" compact />
          </div>

          <div class="mt-4 space-y-1.5">
            <div class="flex items-end justify-between">
              <span class="text-[11px] text-slate-500">装载体积</span>
              <span class="text-[13px] font-semibold tabular-nums text-slate-900">
                {{ cbmText(trip.cbm) }} <span class="text-[11px] font-normal text-slate-400">/ {{ WAREHOUSE_CBM_LIMIT }} CBM</span>
              </span>
            </div>
            <div
              class="h-1.5 overflow-hidden rounded-full bg-slate-100 ring-1 ring-inset ring-slate-200/70"
              role="progressbar"
              :aria-valuenow="percent(trip)"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-label="`${trip.key} 装载体积占 35 CBM 上限`"
            >
              <div
                class="h-full rounded-full transition-[width] duration-500 ease-out"
                :class="tone(trip) === 'red' ? 'bg-gradient-to-r from-red-700 to-red-500' : tone(trip) === 'amber' ? 'bg-gradient-to-r from-amber-600 to-amber-400' : 'bg-gradient-to-r from-teal-700 to-teal-500'"
                :style="{ width: `${percent(trip)}%` }"
              />
            </div>
          </div>

          <div class="mt-3 flex items-center justify-between text-[11px] text-slate-500">
            <span class="inline-flex items-center gap-1">
              <PackageCheck class="size-3.5 text-slate-400" aria-hidden="true" />{{ trip.items }} 条货物
            </span>
            <span class="inline-flex items-center gap-1" :class="trip.cbm > WAREHOUSE_CBM_LIMIT ? 'font-semibold text-red-700' : ''">
              <AlertTriangle v-if="trip.cbm > WAREHOUSE_CBM_LIMIT" class="size-3.5" aria-hidden="true" />
              <CheckCircle2 v-else class="size-3.5 text-emerald-600" aria-hidden="true" />
              {{ trip.cbm > WAREHOUSE_CBM_LIMIT ? '需拆车' : '可装车' }}
            </span>
          </div>
        </article>
      </div>
    </section>

    <p v-if="!warehouseTasks.length" class="rounded-xl border border-dashed border-slate-200 bg-white px-5 py-12 text-center text-[12px] text-slate-500" role="status">
      当前厂区没有交仓分车任务。
    </p>

    <section class="surface-subtle rounded-xl px-4 py-3 text-[11px] leading-5 text-slate-600" aria-label="分车规则">
      <p class="font-semibold text-slate-700">分车口径</p>
      <p>裕泰仓单车不超过 {{ WAREHOUSE_CBM_LIMIT }} CBM；吨车按体积推荐（≤10 → 3T，≤16 → 5T，≤20 → 8T，≤30 → 10T，≤39 → 12T，≤50 → 18T），超过 50 CBM 必须人工指定。同一混装组必须整组同车，件数、体积与卡板合计需与原资料一致。</p>
    </section>
  </div>
</template>

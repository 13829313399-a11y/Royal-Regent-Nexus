<script setup lang="ts">
import { CalendarDays, PackageOpen, SearchX, Siren } from '@lucide/vue'
import CandidateMachinePanel from './CandidateMachinePanel.vue'
import type { BacklogOrder, InjectionMachine } from '@/types/injectionScheduling'

defineProps<{
  orders: BacklogOrder[]
  machines: InjectionMachine[]
  selectedOrder: BacklogOrder | null
}>()

const emit = defineEmits<{
  select: [backlogId: string]
  assign: [backlogId: string, machineId: string]
}>()

function forwardAssignment(backlogId: string, machineId: string) {
  emit('assign', backlogId, machineId)
}
</script>

<template>
  <section class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
    <div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <header class="flex items-center justify-between border-b border-slate-200 bg-[#dfecea] px-5 py-3">
        <div>
          <strong class="text-sm text-slate-800">待排订单池</strong>
          <p class="mt-1 text-[10px] text-slate-500">点击订单查看候选机台；分配动作需二次确认</p>
        </div>
        <span class="rounded-full bg-white px-2.5 py-1 text-[10px] font-black text-amber-700">{{ orders.length }} 条可见</span>
      </header>

      <div v-if="orders.length" class="grid gap-3 p-4 md:grid-cols-2 2xl:grid-cols-3">
        <button
          v-for="order in orders"
          :key="order.id"
          type="button"
          class="rounded-xl border p-4 text-left transition hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-md"
          :class="selectedOrder?.id === order.id ? 'border-teal-400 bg-teal-50/40 ring-2 ring-teal-100' : 'border-slate-200 bg-white'"
          @click="emit('select', order.id)"
        >
          <div class="flex items-start justify-between gap-3">
            <span class="grid size-9 place-items-center rounded-lg bg-slate-100 text-slate-600">
              <PackageOpen class="size-4" aria-hidden="true" />
            </span>
            <span
              class="inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-black"
              :class="order.urgency === 'urgent' ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-slate-600'"
            >
              <Siren v-if="order.urgency === 'urgent'" class="size-3" aria-hidden="true" />
              {{ order.urgency === 'urgent' ? '特急' : '普通' }}
            </span>
          </div>
          <h3 class="mt-4 truncate text-sm font-black text-slate-950">{{ order.moldNo }}</h3>
          <p class="mt-1 truncate text-xs text-slate-500">{{ order.productName }}</p>
          <dl class="mt-4 grid grid-cols-2 gap-2 text-[10px]">
            <div><dt class="text-slate-400">单号</dt><dd class="mt-1 font-bold text-slate-700">{{ order.orderNo }}</dd></div>
            <div><dt class="text-slate-400">欠数</dt><dd class="mt-1 font-bold text-slate-700">{{ order.quantity.toLocaleString() }}</dd></div>
            <div><dt class="text-slate-400">建议机型</dt><dd class="mt-1 font-bold text-slate-700">{{ order.machineType }}</dd></div>
            <div><dt class="text-slate-400">颜色</dt><dd class="mt-1 font-bold text-slate-700">{{ order.color }}</dd></div>
          </dl>
          <p class="mt-4 flex items-center gap-1.5 border-t border-slate-100 pt-3 text-[10px] text-slate-500">
            <CalendarDays class="size-3" aria-hidden="true" />
            要求日期 {{ order.requiredDate }}
          </p>
        </button>
      </div>
      <div v-else class="flex min-h-72 flex-col items-center justify-center text-center">
        <SearchX class="size-6 text-slate-400" aria-hidden="true" />
        <strong class="mt-3 text-sm text-slate-700">没有匹配的待排订单</strong>
        <p class="mt-1 text-xs text-slate-400">请清除搜索条件后重试。</p>
      </div>
    </div>

    <CandidateMachinePanel
      :order="selectedOrder"
      :machines="machines"
      @assign="forwardAssignment"
    />
  </section>
</template>

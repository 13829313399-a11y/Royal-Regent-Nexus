<script setup lang="ts">
import { ArrowLeft, CalendarDays, PackageOpen, SearchX, Siren } from '@lucide/vue'
import CandidateMachinePanel from './CandidateMachinePanel.vue'
import { formatScheduleTime } from '@/lib/injectionSchedulingPresentation'
import type { BacklogOrder, InjectionMachine } from '@/types/injectionScheduling'

defineProps<{
  orders: BacklogOrder[]
  machines: InjectionMachine[]
  selectedOrder: BacklogOrder | null
}>()

const emit = defineEmits<{
  select: [backlogId: string]
  clearSelection: []
  assign: [backlogId: string, machineId: string]
}>()
</script>

<template>
  <div v-if="selectedOrder" class="space-y-4">
    <button type="button" class="inline-flex items-center gap-2 text-[10px] font-black text-teal-700" @click="emit('clearSelection')">
      <ArrowLeft class="size-3" />返回待排列表
    </button>
    <CandidateMachinePanel
      :order="selectedOrder"
      :machines="machines"
      @assign="(backlogId, machineId) => emit('assign', backlogId, machineId)"
    />
  </div>

  <div v-else-if="orders.length" class="space-y-2.5">
    <button
      v-for="order in orders"
      :key="order.id"
      type="button"
      class="w-full rounded-xl border border-slate-200 bg-white p-3 text-left transition hover:border-teal-300 hover:shadow-sm"
      @click="emit('select', order.id)"
    >
      <div class="flex items-start gap-2.5">
        <span class="grid size-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-600">
          <PackageOpen class="size-3.5" aria-hidden="true" />
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <strong class="min-w-0 flex-1 truncate text-[11px] text-slate-900">{{ order.requirement.mold.moldNo }} · {{ order.requirement.productName }}</strong>
            <span
              class="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[8px] font-black"
              :class="order.requirement.priorityCode === 'P0' ? 'bg-orange-100 text-orange-700' : 'bg-teal-50 text-teal-700'"
            >
              <Siren v-if="order.requirement.priorityCode === 'P0'" class="size-2.5" />
              {{ order.requirement.priorityCode === 'P0' ? '特急' : order.requirement.priorityCode }}
            </span>
          </div>
          <p class="mt-1 truncate text-[8px] text-slate-400">{{ order.requirement.orderNo }} · {{ order.requirement.material }} · {{ order.requirement.color }}</p>
        </div>
      </div>
      <dl class="mt-2.5 grid grid-cols-3 gap-2 rounded-lg bg-slate-50 p-2 text-[8px]">
        <div><dt class="text-slate-400">欠数</dt><dd class="mt-0.5 font-black text-slate-700">{{ order.production.remainingQuantity.toLocaleString() }}</dd></div>
        <div><dt class="text-slate-400">整啤毛重</dt><dd class="mt-0.5 font-black text-slate-700">{{ order.requirement.mold.shotWeightGrams ? `${order.requirement.mold.shotWeightGrams}g` : '未录入' }}</dd></div>
        <div><dt class="text-slate-400">候选机台</dt><dd class="mt-0.5 font-black" :class="order.candidates.length ? 'text-teal-700' : 'text-red-600'">{{ order.candidates.length }} 台</dd></div>
      </dl>
      <p class="mt-2 flex items-center gap-1.5 text-[8px] text-slate-500">
        <CalendarDays class="size-2.5" />
        交期 {{ formatScheduleTime(order.requiredDate) }}
        <span v-if="order.noMatchReason" class="ml-auto truncate text-red-600">{{ order.noMatchReason }}</span>
      </p>
    </button>
  </div>

  <div v-else class="flex min-h-72 flex-col items-center justify-center text-center">
    <SearchX class="size-6 text-slate-400" aria-hidden="true" />
    <strong class="mt-3 text-sm text-slate-700">没有匹配的待排订单</strong>
    <p class="mt-1 text-xs text-slate-400">请清除搜索条件后重试。</p>
  </div>
</template>

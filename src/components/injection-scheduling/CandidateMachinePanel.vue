<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Gauge, Sparkles } from '@lucide/vue'
import { computed } from 'vue'
import type { BacklogOrder, InjectionMachine } from '@/types/injectionScheduling'

const props = defineProps<{ order: BacklogOrder | null; machines: InjectionMachine[] }>()
const emit = defineEmits<{ assign: [backlogId: string, machineId: string] }>()

const machineMap = computed(() => new Map(props.machines.map((machine) => [machine.id, machine])))
</script>

<template>
  <aside class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div v-if="order">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-[10px] font-black uppercase tracking-[.16em] text-teal-700">Candidate machines</p>
          <h3 class="mt-2 text-lg font-black text-slate-950">候选机台建议</h3>
          <p class="mt-1 text-xs text-slate-500">{{ order.moldNo }} · {{ order.productName }}</p>
        </div>
        <span class="rounded-full bg-amber-50 px-2 py-1 text-[10px] font-black text-amber-700">前端演示</span>
      </div>

      <div class="mt-4 space-y-3">
        <article
          v-for="candidate in order.candidates"
          :key="candidate.machineId"
          class="rounded-xl border border-slate-200 p-3.5"
        >
          <div class="flex items-center justify-between gap-3">
            <div>
              <strong class="text-sm text-slate-900">{{ machineMap.get(candidate.machineId)?.name ?? candidate.machineId }}</strong>
              <p class="mt-1 text-[10px] font-bold text-teal-700">{{ candidate.title }}</p>
            </div>
            <div class="text-right">
              <strong class="text-xl text-teal-700">{{ candidate.score }}</strong>
              <p class="text-[9px] text-slate-400">适配评分</p>
            </div>
          </div>

          <div class="mt-3 h-1.5 rounded-full bg-slate-100">
            <div class="h-full rounded-full bg-teal-600" :style="{ width: `${candidate.score}%` }" />
          </div>

          <ul class="mt-3 space-y-1.5">
            <li v-for="reason in candidate.reasons" :key="reason" class="flex items-start gap-2 text-[11px] text-slate-600">
              <CheckCircle2 class="mt-0.5 size-3 shrink-0 text-teal-600" aria-hidden="true" />
              {{ reason }}
            </li>
          </ul>

          <p v-if="candidate.warning" class="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-2 text-[10px] leading-4 text-amber-800">
            <AlertTriangle class="mt-0.5 size-3 shrink-0" aria-hidden="true" />
            {{ candidate.warning }}
          </p>

          <button
            type="button"
            class="mt-3 inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg bg-teal-700 px-3 text-xs font-black text-white hover:bg-teal-800"
            @click="emit('assign', order.id, candidate.machineId)"
          >
            <Gauge class="size-3.5" aria-hidden="true" />
            选择此机台
          </button>
        </article>
      </div>
    </div>

    <div v-else class="flex min-h-72 flex-col items-center justify-center px-6 text-center">
      <span class="grid size-12 place-items-center rounded-2xl bg-teal-50 text-teal-700">
        <Sparkles class="size-5" aria-hidden="true" />
      </span>
      <strong class="mt-4 text-sm text-slate-800">选择一张待排订单</strong>
      <p class="mt-2 text-xs leading-5 text-slate-500">这里会展示基于 Mock 约束的候选机台与解释，正式评分由后端负责。</p>
    </div>
  </aside>
</template>


<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Gauge, ShieldX } from '@lucide/vue'
import { computed } from 'vue'
import { formatScheduleTime } from '@/lib/injectionSchedulingPresentation'
import type { BacklogOrder, InjectionMachine } from '@/types/injectionScheduling'

const props = defineProps<{ order: BacklogOrder; machines: InjectionMachine[] }>()
const emit = defineEmits<{ assign: [backlogId: string, machineId: string] }>()

const machineMap = computed(() => new Map(props.machines.map((machine) => [machine.id, machine])))
</script>

<template>
  <section>
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-[9px] font-black uppercase tracking-[.16em] text-teal-700">Candidate machines</p>
        <h3 class="mt-1 text-base font-black text-slate-950">候选机台与匹配解释</h3>
        <p class="mt-1 text-[10px] text-slate-500">{{ order.requirement.mold.moldNo }} · {{ order.requirement.productName }}</p>
      </div>
      <span class="rounded-full bg-amber-50 px-2 py-1 text-[8px] font-black text-amber-700">前端草案</span>
    </div>

    <div v-if="order.candidates.length" class="mt-4 space-y-3">
      <article
        v-for="candidate in order.candidates"
        :key="candidate.machineId"
        class="rounded-xl border border-slate-200 p-3.5"
      >
        <div class="flex items-center justify-between gap-3">
          <div>
            <strong class="text-[12px] text-slate-900">{{ machineMap.get(candidate.machineId)?.name ?? candidate.machineId }}</strong>
            <p class="mt-1 text-[8px] font-bold text-teal-700">{{ candidate.title }}</p>
          </div>
          <div class="text-right">
            <strong class="text-xl text-teal-700">{{ candidate.score }}</strong>
            <p class="text-[7px] text-slate-400">适配评分</p>
          </div>
        </div>

        <div class="mt-3 h-1.5 rounded-full bg-slate-100">
          <div class="h-full rounded-full bg-teal-600" :style="{ width: `${candidate.score}%` }" />
        </div>

        <div class="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-2 text-[8px]">
          <span>插入位置 <b class="block text-slate-700">{{ candidate.insertionLabel }}</b></span>
          <span>预计完成 <b class="block text-slate-700">{{ formatScheduleTime(candidate.projectedEndAt) }}</b></span>
        </div>

        <div class="mt-3 space-y-1">
          <div
            v-for="check in candidate.eligibility.checks"
            :key="check.code"
            class="flex items-start gap-2 text-[8px]"
            :class="check.passed ? 'text-slate-600' : 'text-red-700'"
          >
            <CheckCircle2 v-if="check.passed" class="mt-0.5 size-2.5 shrink-0 text-teal-600" />
            <ShieldX v-else class="mt-0.5 size-2.5 shrink-0" />
            <span><b>{{ check.label }}</b> · {{ check.reason }}</span>
          </div>
        </div>

        <details class="mt-3 rounded-lg border border-slate-100 p-2">
          <summary class="cursor-pointer text-[8px] font-black text-slate-600">查看评分分项</summary>
          <ul class="mt-2 grid grid-cols-2 gap-1.5">
            <li v-for="item in candidate.breakdown" :key="item.key" class="rounded bg-slate-50 p-1.5 text-[8px] text-slate-500">
              {{ item.label }} <b class="float-right text-teal-700">+{{ item.score.toFixed(0) }}</b>
              <span class="mt-0.5 block">{{ item.reason }}</span>
            </li>
          </ul>
        </details>

        <p v-if="candidate.warning" class="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-2 text-[8px] leading-4 text-amber-800">
          <AlertTriangle class="mt-0.5 size-3 shrink-0" />
          {{ candidate.warning }}
        </p>

        <button
          type="button"
          class="mt-3 inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg bg-teal-700 px-3 text-[10px] font-black text-white hover:bg-teal-800"
          @click="emit('assign', order.id, candidate.machineId)"
        >
          <Gauge class="size-3.5" />
          选择此机台并进入确认
        </button>
      </article>
    </div>

    <div v-else class="mt-4 rounded-xl border border-red-100 bg-red-50 p-4">
      <strong class="flex items-center gap-2 text-[11px] text-red-800"><ShieldX class="size-4" />无合格候选机台</strong>
      <p class="mt-2 text-[9px] leading-5 text-red-700">{{ order.noMatchReason }}</p>
    </div>
  </section>
</template>

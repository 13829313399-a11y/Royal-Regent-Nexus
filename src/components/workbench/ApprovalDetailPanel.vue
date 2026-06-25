<script setup lang="ts">
import type { Tone } from '@/data/enterpriseMock'
import { approvalSteps, type ApprovalRow } from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'

defineProps<{
  approval: ApprovalRow
}>()

const stepToneClasses: Record<'done' | 'active' | 'pending', string> = {
  done: 'bg-teal-700',
  active: 'bg-amber-600',
  pending: 'bg-slate-200',
}

const ownerToneClasses: Record<'done' | 'active' | 'pending', string> = {
  done: 'text-slate-500',
  active: 'text-amber-700',
  pending: 'text-slate-500',
}

const riskTone: Tone = 'amber'
</script>

<template>
  <SectionPanel title="审批详情">
    <template #action>
      <StatusPill :label="approval.status" :tone="approval.statusTone" compact />
    </template>

    <p class="mb-5 text-sm text-slate-500">{{ approval.id }}</p>

    <div class="rounded-lg border border-slate-200 bg-slate-50 p-5">
      <h3 class="font-semibold text-slate-950">{{ approval.customer }} · 报价变更</h3>
      <div class="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-700">
        <span>厂区：{{ approval.factory }}</span>
        <span>金额：{{ approval.amount }}</span>
      </div>
      <p class="mt-4 text-xs leading-5 text-slate-500">
        客户要求提前交期，涉及工程工艺和 PMC 物料复核。
      </p>
    </div>

    <div class="mt-7">
      <h3 class="mb-5 font-semibold text-slate-950">流程进度</h3>
      <div class="space-y-7">
        <div v-for="(step, index) in approvalSteps" :key="step.label" class="relative grid grid-cols-[24px_1fr_auto] gap-3">
          <span
            class="mt-1 size-3 rounded-full"
            :class="stepToneClasses[step.state]"
          />
          <span
            v-if="index !== approvalSteps.length - 1"
            class="absolute left-[5px] top-5 h-11 w-px bg-slate-200"
          />
          <span class="text-sm text-slate-800">{{ step.label }}</span>
          <span class="text-xs" :class="ownerToneClasses[step.state]">{{ step.owner }}</span>
        </div>
      </div>
    </div>

    <div class="mt-8 rounded-lg border border-amber-200 bg-amber-50 p-5">
      <StatusPill label="风险提示" :tone="riskTone" compact />
      <p class="mt-3 text-xs leading-5 text-amber-800">
        物料到料日期晚于客户要求交期 1 天，建议审批前确认替代料。
      </p>
    </div>

    <div class="mt-8 grid grid-cols-3 gap-3">
      <button type="button" class="h-10 rounded-lg border border-slate-200 bg-white text-sm text-slate-700">
        退回
      </button>
      <button type="button" class="h-10 rounded-lg border border-slate-200 bg-white text-sm text-slate-700">
        转交
      </button>
      <button type="button" class="h-10 rounded-lg bg-teal-700 text-sm font-semibold text-white">
        通过
      </button>
    </div>
  </SectionPanel>
</template>

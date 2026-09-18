<script setup lang="ts">
import { ShieldAlert } from '@lucide/vue'
import type { Tone } from '@/data/enterpriseMock'
import { approvalSteps, type ApprovalRow } from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'

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
  <SectionPanel class="wb-detail xl:sticky xl:top-[99px] xl:self-start" title="审批详情">
    <template #action>
      <StatusPill :label="approval.status" :tone="approval.statusTone" compact />
    </template>

    <p class="mb-5 text-sm text-slate-500">{{ approval.id }}</p>

    <div class="wb-detail__card surface-subtle rounded-xl p-5">
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
      <h3 class="wb-detail__steps-title mb-5 font-semibold text-slate-950">流程进度</h3>
      <div class="space-y-7">
        <div v-for="(step, index) in approvalSteps" :key="step.label" class="relative grid grid-cols-[24px_1fr_auto] gap-3">
          <span
            class="mt-1 size-3 rounded-full ring-4 ring-white shadow-sm"
            :class="stepToneClasses[step.state]"
          />
          <span
            v-if="index !== approvalSteps.length - 1"
            class="absolute left-[5px] top-5 h-11 w-px bg-gradient-to-b from-slate-300 to-slate-100"
          />
          <span class="text-sm text-slate-800">{{ step.label }}</span>
          <span class="text-xs" :class="ownerToneClasses[step.state]">{{ step.owner }}</span>
        </div>
      </div>
    </div>

    <div class="mt-8 rounded-xl border border-amber-200 bg-gradient-to-br from-amber-50 to-white p-5 shadow-[inset_3px_0_0_rgba(217,119,6,0.55)]">
      <div class="flex items-center gap-2">
        <ShieldAlert class="size-4 text-amber-700" aria-hidden="true" />
        <StatusPill label="风险提示" :tone="riskTone" compact />
      </div>
      <p class="mt-3 text-xs leading-5 text-amber-800">
        物料到料日期晚于客户要求交期 1 天，建议审批前确认替代料。
      </p>
    </div>

    <div class="mt-8 grid grid-cols-3 gap-3">
      <Button type="button" variant="destructive" size="lg" class="w-full px-2">
        退回
      </Button>
      <Button type="button" variant="outline" size="lg" class="w-full px-2">
        转交
      </Button>
      <Button type="button" size="lg" class="w-full px-2">
        通过
      </Button>
    </div>
  </SectionPanel>
</template>

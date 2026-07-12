<script setup lang="ts">
import { approvalRows } from '@/data/enterpriseMock'
import StatusPill from '@/components/common/StatusPill.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'

defineProps<{
  selectedId: string
}>()

const emit = defineEmits<{
  select: [approvalId: string]
}>()
</script>

<template>
  <SectionPanel title="审批列表">
    <template #action>
      <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold tabular-nums text-slate-600 ring-1 ring-inset ring-slate-200">共 128 条</span>
    </template>

    <div class="overflow-x-auto">
      <div class="min-w-[664px]">
        <div class="grid grid-cols-[1.3fr_1.1fr_0.7fr_0.9fr_0.8fr_0.5fr] rounded-lg border border-slate-200/80 bg-slate-50/80 px-5 py-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          <span>单号</span>
          <span>客户</span>
          <span>厂区</span>
          <span>状态</span>
          <span>负责人</span>
          <span>SLA</span>
        </div>

        <div class="mt-3 space-y-3">
          <button
            v-for="row in approvalRows"
            :key="row.id"
            type="button"
            class="grid w-full grid-cols-[1.3fr_1.1fr_0.7fr_0.9fr_0.8fr_0.5fr] items-center rounded-xl border px-5 py-4 text-left transition-[background-color,border-color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/30"
            :class="row.id === selectedId
              ? 'border-teal-300 bg-gradient-to-r from-teal-50 to-white shadow-[inset_3px_0_0_rgba(13,148,136,0.75),0_8px_20px_-18px_rgba(13,148,136,0.8)]'
              : 'border-slate-200 bg-white hover:-translate-y-px hover:border-slate-300 hover:bg-slate-50/70 hover:shadow-sm'"
            :aria-pressed="row.id === selectedId"
            @click="emit('select', row.id)"
          >
            <span>
              <span class="block font-semibold text-slate-950">{{ row.id }}</span>
              <span class="mt-1 block text-xs text-slate-500">{{ row.summary }}</span>
            </span>
            <span class="text-sm text-slate-800">{{ row.customer }}</span>
            <span class="text-sm text-slate-800">{{ row.factory }}</span>
            <span><StatusPill :label="row.status" :tone="row.statusTone" compact /></span>
            <span class="text-sm text-slate-800">{{ row.owner }}</span>
            <span
              class="w-fit rounded-md px-2 py-1 text-xs font-bold tabular-nums"
              :class="row.sla === '2h' ? 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-100' : 'bg-slate-100 text-slate-700'"
            >
              {{ row.sla }}
            </span>
          </button>
        </div>
      </div>
    </div>
  </SectionPanel>
</template>

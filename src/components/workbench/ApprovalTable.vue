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
      <span class="text-sm text-slate-500">共 128 条</span>
    </template>

    <div class="overflow-x-auto">
      <div class="min-w-[664px]">
        <div class="grid grid-cols-[1.3fr_1.1fr_0.7fr_0.9fr_0.8fr_0.5fr] rounded-lg bg-slate-50 px-5 py-3 text-xs text-slate-500">
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
            class="grid w-full grid-cols-[1.3fr_1.1fr_0.7fr_0.9fr_0.8fr_0.5fr] items-center rounded-lg border px-5 py-4 text-left transition-colors"
            :class="row.id === selectedId
              ? 'border-teal-600 bg-teal-50'
              : 'border-slate-200 bg-white hover:bg-slate-50'"
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
              class="text-sm font-semibold"
              :class="row.sla === '2h' ? 'text-red-700' : 'text-slate-800'"
            >
              {{ row.sla }}
            </span>
          </button>
        </div>
      </div>
    </div>
  </SectionPanel>
</template>

<script setup lang="ts">
import { Box, CheckCircle2, ListChecks, ShieldCheck } from '@lucide/vue'

export type InspectorTab = 'sources' | 'tasks' | 'artifacts' | 'actions'

defineProps<{
  activeTab: InspectorTab
  counts: Record<InspectorTab, number>
}>()

const emit = defineEmits<{
  tab: [tab: InspectorTab]
}>()

const tabs = [
  { id: 'sources' as const, label: '来源', icon: ShieldCheck },
  { id: 'tasks' as const, label: '任务', icon: ListChecks },
  { id: 'artifacts' as const, label: '产物', icon: Box },
  { id: 'actions' as const, label: '操作', icon: CheckCircle2 },
]
</script>

<template>
  <section class="flex h-full min-h-0 flex-col" aria-label="上下文检查器">
    <div class="border-b border-slate-200 px-3 pb-2 pt-3 pr-11">
      <h2 class="text-xs font-bold text-slate-900">上下文检查器</h2>
      <div class="mt-2 grid grid-cols-4 gap-1" role="tablist" aria-label="检查器内容">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          role="tab"
          class="flex min-w-0 flex-col items-center gap-1 rounded-lg px-1 py-1.5 text-[10px] font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
          :class="activeTab === tab.id ? 'bg-sky-50 text-sky-800' : 'text-slate-500 hover:bg-slate-50'"
          :aria-selected="activeTab === tab.id"
          @click="emit('tab', tab.id)"
        >
          <component :is="tab.icon" class="size-3.5" aria-hidden="true" />
          <span>{{ tab.label }}<span v-if="counts[tab.id]"> {{ counts[tab.id] }}</span></span>
        </button>
      </div>
    </div>
    <div class="min-h-0 flex-1 overflow-y-auto" role="tabpanel">
      <slot :name="activeTab" />
    </div>
  </section>
</template>

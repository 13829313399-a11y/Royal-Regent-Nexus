<script setup lang="ts">
import { Database, FileText, Lightbulb, UserRound } from '@lucide/vue'
import type { AISourceSummary } from '@/features/ai-assistant/types'

defineProps<{ source: AISourceSummary }>()

const factoryLabels: Record<string, string> = {
  'huakang-a': '华康 A',
  'huakang-b': '华康 B',
  'huakang-c': '华康 C',
  'huakang-d': '华康 D',
  huadeng: '华登',
  huaxing: '华兴',
}

function time(value?: string) {
  if (!value || !Number.isFinite(Date.parse(value))) return ''
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}
</script>

<template>
  <span class="inline-flex max-w-full items-center gap-1 rounded-full border border-border bg-card px-2 py-1 text-[11px] font-semibold text-muted-foreground">
    <Database v-if="source.level === 'FORMAL'" class="size-3 text-emerald-600" aria-hidden="true" />
    <FileText v-else-if="source.level === 'MODULE_KNOWLEDGE'" class="size-3 text-sky-600" aria-hidden="true" />
    <UserRound v-else-if="source.level === 'USER_PROVIDED'" class="size-3 text-amber-600" aria-hidden="true" />
    <Lightbulb v-else class="size-3 text-violet-600" aria-hidden="true" />
    <span class="truncate">{{ source.label }}</span>
    <span v-if="source.factoryId" class="shrink-0 font-normal">· {{ factoryLabels[source.factoryId] ?? '当前厂区' }}</span>
    <span v-if="time(source.updatedAt)" class="shrink-0 font-normal">· {{ time(source.updatedAt) }}</span>
  </span>
</template>

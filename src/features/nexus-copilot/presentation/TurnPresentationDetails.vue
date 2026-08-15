<script setup lang="ts">
import { History, RefreshCcw } from '@lucide/vue'
import type { AITurnPresentation } from '@/features/ai-assistant/types'
import AiToolActivity from '@/features/ai-assistant/AiToolActivity.vue'
import ResultRendererHost from './ResultRendererHost.vue'
import SourceChip from './SourceChip.vue'

defineProps<{ turn: AITurnPresentation }>()
</script>

<template>
  <div
    v-if="turn.activities.length || turn.businessResults.length || turn.sources.length || turn.historical"
    class="ml-11 mt-2 max-w-[min(100%,960px)] space-y-2"
    :data-turn-id="turn.id"
  >
    <div
      v-if="turn.historical && turn.requiresRefresh"
      class="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-[11px] leading-4 text-amber-900"
    >
      <History class="size-3.5 shrink-0" aria-hidden="true" />
      历史展示快照，不代表当前正式数据；查询最新事实时会按当前权限重新读取。
      <RefreshCcw class="ml-auto size-3.5 shrink-0" aria-hidden="true" />
    </div>
    <AiToolActivity :items="turn.activities" />
    <ResultRendererHost :results="turn.businessResults" :sources="turn.sources" />
    <div v-if="turn.sources.length" class="flex flex-wrap gap-1.5" aria-label="本轮回答来源">
      <SourceChip v-for="source in turn.sources" :key="source.id" :source="source" />
    </div>
  </div>
</template>

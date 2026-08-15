<script setup lang="ts">
import type { AIBusinessResult, AISourceSummary } from '@/features/ai-assistant/types'
import { resultRendererFor } from './resultRendererRegistry'
import SourcesPanel from './SourcesPanel.vue'

defineProps<{ results: AIBusinessResult[]; sources: AISourceSummary[] }>()
</script>

<template>
  <div v-if="results.length || sources.length" data-result-renderer-host data-ai-business-results>
    <component
      :is="resultRendererFor(result.kind)"
      v-for="result in results"
      :key="result.id"
      :result="result"
      :sources="[]"
    />
    <SourcesPanel :sources="sources" />
  </div>
</template>

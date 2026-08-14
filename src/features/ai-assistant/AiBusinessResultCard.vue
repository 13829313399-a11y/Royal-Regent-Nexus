<script setup lang="ts">
import ResultRendererHost from '@/features/nexus-copilot/presentation/ResultRendererHost.vue'
import type { AIBusinessResult, AISourceSummary } from './types'

defineProps<{
  results: AIBusinessResult[]
  sources: AISourceSummary[]
}>()
</script>

<template>
  <ResultRendererHost :results="results" :sources="sources" />
</template>

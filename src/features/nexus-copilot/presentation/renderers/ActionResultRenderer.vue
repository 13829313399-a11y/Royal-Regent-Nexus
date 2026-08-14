<script setup lang="ts">
import AiActionConfirmationCard from '@/features/ai-assistant/AiActionConfirmationCard.vue'
import type { AIBusinessResult, AISourceSummary } from '@/features/ai-assistant/types'
import ResultFrame from '../ResultFrame.vue'

defineProps<{ result: AIBusinessResult; sources: AISourceSummary[] }>()
</script>

<template>
  <ResultFrame :result="result">
    <AiActionConfirmationCard v-if="result.actionConfirmation" :confirmation="result.actionConfirmation" />
  </ResultFrame>
</template>

<script setup lang="ts">
import type { DocumentProcessingMode, DocumentToolCapability } from '@/api/tools'
import ProcessingModePanel from './ProcessingModePanel.vue'

defineProps<{ mode: DocumentProcessingMode; capability: DocumentToolCapability | null; disabled?: boolean }>()
const emit = defineEmits<{ 'update:mode': [mode: DocumentProcessingMode] }>()
</script>

<template>
  <ProcessingModePanel :model-value="mode" :capability="capability" :disabled="disabled" @update:model-value="emit('update:mode', $event)" />
  <p class="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">自动模式只把扫描页或低置信页交给千问；结构化 JSON 会直接写入 Excel，并保留前导零。</p>
</template>

<script setup lang="ts">
import type { DocumentProcessingMode, DocumentToolCapability } from '@/api/tools'
import ProcessingModePanel from './ProcessingModePanel.vue'

defineProps<{ mode: DocumentProcessingMode; capability: DocumentToolCapability | null; disabled?: boolean }>()
const emit = defineEmits<{ 'update:mode': [mode: DocumentProcessingMode] }>()
</script>

<template>
  <ProcessingModePanel :model-value="mode" :capability="capability" :disabled="disabled" @update:model-value="emit('update:mode', $event)" />
  <p class="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">自动模式使用服务器本地文字与 OCR 引擎提取表格，并保留前导零。</p>
</template>

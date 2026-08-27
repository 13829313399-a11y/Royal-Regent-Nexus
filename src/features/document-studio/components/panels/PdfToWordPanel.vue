<script setup lang="ts">
import type { DocumentProcessingMode, DocumentToolCapability } from '@/api/tools'
import ProcessingModePanel from './ProcessingModePanel.vue'

defineProps<{
  mode: DocumentProcessingMode
  outputMode: 'EDITABLE' | 'LAYOUT_PRESERVING'
  capability: DocumentToolCapability | null
  disabled?: boolean
}>()
const emit = defineEmits<{
  'update:mode': [mode: DocumentProcessingMode]
  'update:outputMode': [mode: 'EDITABLE' | 'LAYOUT_PRESERVING']
}>()
</script>

<template>
  <ProcessingModePanel :model-value="mode" :capability="capability" :disabled="disabled" @update:model-value="emit('update:mode', $event)" />
  <div>
    <p class="text-xs font-semibold text-slate-700">输出方式</p>
    <div class="mt-2 grid grid-cols-2 gap-2">
      <button type="button" class="rounded-lg border px-2 py-2 text-xs font-semibold" :class="outputMode === 'EDITABLE' ? 'border-teal-400 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600'" :disabled="disabled" @click="emit('update:outputMode', 'EDITABLE')">可编辑优先</button>
      <button type="button" class="rounded-lg border px-2 py-2 text-xs font-semibold" :class="outputMode === 'LAYOUT_PRESERVING' ? 'border-teal-400 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600'" :disabled="disabled" @click="emit('update:outputMode', 'LAYOUT_PRESERVING')">版式保真</button>
    </div>
  </div>
  <p class="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">{{ outputMode === 'EDITABLE' ? '原生文字页保持可编辑；扫描页使用服务器本地 OCR。' : '每页作为清晰页面图像写入 Word，版式更稳定但文字不可直接编辑。' }}</p>
</template>

<script setup lang="ts">
import type { DocumentProcessingMode, DocumentToolCapability } from '@/api/tools'
import ProcessingModePanel from './ProcessingModePanel.vue'

defineProps<{
  mode: DocumentProcessingMode
  capability: DocumentToolCapability | null
  direction: 'AUTO' | 'ZH_TO_EN' | 'EN_TO_ZH'
  layout: 'TRANSLATED_ONLY' | 'SIDE_BY_SIDE' | 'STACKED'
  protectedTokens: string
  includeEditableDocx: boolean
  glossaryText: string
  translationMemoryText: string
  domainPrompt: string
  disabled?: boolean
}>()
const emit = defineEmits<{
  'update:mode': [value: DocumentProcessingMode]
  'update:direction': [value: 'AUTO' | 'ZH_TO_EN' | 'EN_TO_ZH']
  'update:layout': [value: 'TRANSLATED_ONLY' | 'SIDE_BY_SIDE' | 'STACKED']
  'update:protectedTokens': [value: string]
  'update:includeEditableDocx': [value: boolean]
  'update:glossaryText': [value: string]
  'update:translationMemoryText': [value: string]
  'update:domainPrompt': [value: string]
}>()
</script>

<template>
  <ProcessingModePanel :model-value="mode" :capability="capability" :disabled="disabled" @update:model-value="emit('update:mode', $event)" />
  <label class="block text-xs font-semibold text-slate-700">翻译方向<select :value="direction" class="mt-2 h-9 w-full rounded-lg border border-slate-300 bg-white px-2 text-xs" :disabled="disabled" @change="emit('update:direction', ($event.target as HTMLSelectElement).value as typeof direction)"><option value="AUTO">自动识别</option><option value="ZH_TO_EN">中文 → 英文</option><option value="EN_TO_ZH">英文 → 中文</option></select></label>
  <label class="block text-xs font-semibold text-slate-700">输出版式<select :value="layout" class="mt-2 h-9 w-full rounded-lg border border-slate-300 bg-white px-2 text-xs" :disabled="disabled" @change="emit('update:layout', ($event.target as HTMLSelectElement).value as typeof layout)"><option value="TRANSLATED_ONLY">仅译文</option><option value="SIDE_BY_SIDE">左右双语</option><option value="STACKED">上下双语</option></select></label>
  <details>
    <summary class="cursor-pointer text-xs font-semibold text-slate-700">高级设置</summary>
    <label class="mt-3 block text-xs font-semibold text-slate-700">保护词（逗号或换行分隔）<textarea :value="protectedTokens" class="mt-2 min-h-16 w-full rounded-lg border border-slate-300 p-2 text-xs" placeholder="订单号、料号、型号" :disabled="disabled" @input="emit('update:protectedTokens', ($event.target as HTMLTextAreaElement).value)" /></label>
    <label class="mt-3 block text-xs font-semibold text-slate-700">术语表（每行：源词 =&gt; 译词）<textarea :value="glossaryText" class="mt-2 min-h-16 w-full rounded-lg border border-slate-300 p-2 text-xs" placeholder="模具 => mold" :disabled="disabled" @input="emit('update:glossaryText', ($event.target as HTMLTextAreaElement).value)" /></label>
    <label class="mt-3 block text-xs font-semibold text-slate-700">翻译记忆（每行：源句 =&gt; 译句）<textarea :value="translationMemoryText" class="mt-2 min-h-16 w-full rounded-lg border border-slate-300 p-2 text-xs" placeholder="本订单不可拆分。 => This order cannot be split." :disabled="disabled" @input="emit('update:translationMemoryText', ($event.target as HTMLTextAreaElement).value)" /></label>
    <label class="mt-3 block text-xs font-semibold text-slate-700">领域提示<input :value="domainPrompt" class="mt-2 h-9 w-full rounded-lg border border-slate-300 px-2 text-xs" placeholder="例如：注塑制造订单" :disabled="disabled" @input="emit('update:domainPrompt', ($event.target as HTMLInputElement).value)" /></label>
    <label class="mt-3 flex items-center gap-2 text-xs text-slate-700"><input :checked="includeEditableDocx" type="checkbox" :disabled="disabled" @change="emit('update:includeEditableDocx', ($event.target as HTMLInputElement).checked)">同时输出可编辑 DOCX（ZIP）</label>
  </details>
</template>

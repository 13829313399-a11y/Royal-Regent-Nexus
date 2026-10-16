<script setup lang="ts">
import { computed } from 'vue'
import type { PaperQuantityRule, QuantityPaper } from '@/features/carton-procurement/paperQuantity'
const props = defineProps<{ modelValue?: PaperQuantityRule | null; lines: QuantityPaper[]; index: number; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [PaperQuantityRule] }>()
const parents = computed(() => props.lines.map((line, i) => ({ line, no: i + 1 })).filter(row => row.no !== props.index + 1 && row.line.quantity_rule?.mode !== 'PER_CARTON'))
function mode(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  emit('update:modelValue', value === 'PER_CARTON'
    ? { mode: 'PER_CARTON', carton_line_no: parents.value.length === 1 ? parents.value[0]!.no : null, per_carton_quantity: 1, manual_quantity: props.modelValue?.manual_quantity ?? null }
    : { mode: 'PACKING', manual_quantity: props.modelValue?.manual_quantity ?? null })
}
function patch(values: Partial<PaperQuantityRule>) { emit('update:modelValue', { mode: 'PACKING', ...props.modelValue, ...values }) }
</script>
<template>
  <fieldset :disabled="disabled" class="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2 text-xs disabled:opacity-60">
    <label class="flex min-w-0 max-w-full flex-wrap items-center gap-2"><span class="shrink-0 text-slate-500">数量计算</span><select :value="modelValue?.mode || 'PACKING'" :aria-label="`数量计算 ${index + 1}`" class="h-9 min-w-0 max-w-full rounded-lg border border-slate-200 bg-white px-2" @change="mode"><option value="PACKING">产品数 ÷ 装箱数</option><option value="PER_CARTON">纸箱数 × 配套用量</option></select></label>
    <template v-if="modelValue?.mode === 'PER_CARTON'">
      <label class="flex min-w-0 max-w-full flex-wrap items-center gap-2"><span class="shrink-0 text-slate-500">对应纸箱</span><select :value="modelValue.carton_line_no ?? ''" :aria-label="`对应纸箱 ${index + 1}`" class="h-9 min-w-0 max-w-full rounded-lg border border-slate-200 bg-white px-2" @change="patch({ carton_line_no: Number(($event.target as HTMLSelectElement).value) || null })"><option value="">请选择</option><option v-for="parent in parents" :key="parent.no" :value="parent.no">第 {{ parent.no }} 项 · {{ parent.line.packaging_type || '未命名' }}</option></select></label>
      <label class="flex flex-wrap items-center gap-2"><span class="shrink-0 text-slate-500">每箱配</span><input :value="modelValue.per_carton_quantity" :aria-label="`每箱配套用量 ${index + 1}`" type="number" min="0.0001" step="0.0001" class="h-9 w-20 rounded-lg border border-slate-200 bg-white px-2 text-right" @input="patch({ per_carton_quantity: ($event.target as HTMLInputElement).value })"><span class="text-slate-500">张／个</span></label>
    </template>
  </fieldset>
</template>

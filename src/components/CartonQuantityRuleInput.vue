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
  <fieldset :disabled="disabled" class="flex flex-wrap items-center gap-2 text-xs disabled:opacity-60">
    <label>数量计算 <select :value="modelValue?.mode || 'PACKING'" :aria-label="`数量计算 ${index + 1}`" class="h-8 rounded border bg-white px-2" @change="mode"><option value="PACKING">产品数 ÷ 装箱数</option><option value="PER_CARTON">纸箱数 × 配套用量</option></select></label>
    <template v-if="modelValue?.mode === 'PER_CARTON'">
      <label>对应纸箱 <select :value="modelValue.carton_line_no ?? ''" :aria-label="`对应纸箱 ${index + 1}`" class="h-8 rounded border bg-white px-2" @change="patch({ carton_line_no: Number(($event.target as HTMLSelectElement).value) || null })"><option value="">请选择</option><option v-for="parent in parents" :key="parent.no" :value="parent.no">第 {{ parent.no }} 项 · {{ parent.line.packaging_type || '未命名' }}</option></select></label>
      <label>每箱配 <input :value="modelValue.per_carton_quantity" :aria-label="`每箱配套用量 ${index + 1}`" type="number" min="0.0001" step="0.0001" class="h-8 w-20 rounded border px-2 text-right" @input="patch({ per_carton_quantity: ($event.target as HTMLInputElement).value })"> 张／个</label>
    </template>
  </fieldset>
</template>

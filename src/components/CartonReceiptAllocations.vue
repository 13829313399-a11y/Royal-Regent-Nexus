<script setup lang="ts">
import { watch } from 'vue'
import CartonLocationPicker from './CartonLocationPicker.vue'
import type { CartonLocation, LocationAllocation } from '@/api/cartonPositions'
const props = defineProps<{ modelValue?: LocationAllocation[]; effective: number; locations: CartonLocation[]; factoryId: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [LocationAllocation[]]; created: [] }>()
function change(index: number, values: Partial<LocationAllocation>) {
  const rows = (props.modelValue?.length ? props.modelValue : [{ location_id: '', quantity: props.effective }]).map(row => ({ ...row }))
  rows[index] = { ...rows[index]!, ...values }; emit('update:modelValue', rows)
}
function add() {
  const rows = props.modelValue?.length ? [...props.modelValue] : [{ location_id: '', quantity: props.effective }]
  emit('update:modelValue', [...rows, { location_id: '', quantity: 0 }])
}
function remove(index: number) {
  const rows = (props.modelValue || []).filter((_, i) => i !== index)
  if (rows.length === 1) rows[0] = { ...rows[0]!, quantity: props.effective }
  emit('update:modelValue', rows)
}
watch(() => props.effective, value => {
  if (!props.disabled && props.modelValue?.length === 1) change(0, { quantity: value })
})
</script>
<template>
  <div v-if="effective > 0" class="min-w-64 space-y-2 text-left">
    <div v-for="(part, index) in modelValue?.length ? modelValue : [{ location_id: '', quantity: effective }]" :key="index" class="flex items-start gap-2">
      <CartonLocationPicker :model-value="part.location_id" :locations="locations" :factory-id="factoryId" :disabled="disabled" @update:model-value="change(index, { location_id: $event })" @created="emit('created')" />
      <input v-if="(modelValue?.length || 0) > 1" :value="part.quantity" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="分仓入库数量" class="h-9 w-20 rounded-lg border px-2 text-right text-xs" @input="change(index, { quantity: ($event.target as HTMLInputElement).value })">
      <button v-if="!disabled && (modelValue?.length || 0) > 1" type="button" aria-label="移除分仓" class="pt-2 text-red-600" @click="remove(index)">×</button>
    </div>
    <button v-if="!disabled" type="button" class="text-xs font-semibold text-teal-700" @click="add">＋分仓存放</button>
    <p v-if="(modelValue?.length || 0) > 1" class="text-[10px]" :class="Math.abs((modelValue || []).reduce((sum, row) => sum + Number(row.quantity || 0), 0) - effective) > 0.00001 ? 'text-red-600' : 'text-teal-700'">分仓合计 {{ (modelValue || []).reduce((sum, row) => sum + Number(row.quantity || 0), 0) }} / 有效入库 {{ effective }}</p>
  </div>
  <span v-else class="text-slate-400">无有效入库</span>
</template>

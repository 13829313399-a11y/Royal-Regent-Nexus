<script setup lang="ts">
import CartonPaperPicker from './CartonPaperPicker.vue'
import CartonDimensionInput from './CartonDimensionInput.vue'
import { X } from '@lucide/vue'
withDefaults(defineProps<{ index: number; disabled?: boolean; identityLocked?: boolean; removeDisabled?: boolean; packagingOptions?: string[]; qualityOptions?: string[]; specificationOptions?: string[]; unitOptions?: string[]; dimensionEditable?: boolean; preferredUnit?: 'cm' | 'inch' | 'mm'; itemEnabled?: boolean }>(), { packagingOptions: () => [], qualityOptions: () => [], specificationOptions: () => [], unitOptions: () => [] })
const packaging = defineModel<string>('packaging', { required: true })
const quality = defineModel<string>('quality', { required: true })
const specification = defineModel<string>('specification', { required: true })
const dimension = defineModel<string>('dimension', { required: true })
const unit = defineModel<string>('unit', { required: true })
const item = defineModel<string>('item', { default: '' })
const emit = defineEmits<{ remove: [] }>()
</script>
<template>
  <div class="carton-paper-editor space-y-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
    <div class="carton-paper-fields grid items-start gap-3">
      <label class="min-w-0 space-y-1.5"><span class="block text-[11px] font-bold leading-4 text-slate-500">纸品类型 *</span><CartonPaperPicker v-model="packaging" :options="packagingOptions" :label="`纸品类型 ${index + 1}`" :disabled="disabled || identityLocked" /></label>
      <label class="min-w-0 space-y-1.5"><span class="block text-[11px] font-bold leading-4 text-slate-500">纸质 *</span><CartonPaperPicker v-model="quality" :options="qualityOptions" :label="`纸质 ${index + 1}`" :disabled="disabled || identityLocked" /></label>
      <div class="carton-paper-specification min-w-0 space-y-1.5"><span class="block text-[11px] font-bold leading-4 text-slate-500">规格 *</span><CartonPaperPicker v-model="specification" dimension-paste :options="specificationOptions" :label="`规格 ${index + 1}`" :disabled="disabled || identityLocked" /><label v-if="dimensionEditable" class="block space-y-1 text-xs"><span class="block whitespace-nowrap text-slate-500">尺寸单位</span><select v-model="dimension" :aria-label="`纸品尺寸单位 ${index + 1}`" :disabled="disabled || identityLocked" class="h-9 w-full rounded-lg border bg-white px-2"><option value="cm">cm</option><option value="in">inch</option></select></label><CartonDimensionInput v-else v-model="dimension" :specification="specification" :label="`纸品尺寸显示 ${index + 1}`" readonly show-reference :preferred-unit="preferredUnit" /></div>
      <slot name="basis"><label v-if="itemEnabled" class="min-w-0 space-y-1.5"><span class="block text-[11px] font-bold leading-4 text-slate-500">货号（选填）</span><input v-model="item" :aria-label="`纸品货号 ${index + 1}`" :disabled="disabled || identityLocked" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2"></label></slot>
      <slot name="quantity" />
      <label class="min-w-0 space-y-1.5"><span class="block text-[11px] font-bold leading-4 text-slate-500">单位 *</span><select v-if="unitOptions.length" v-model="unit" :aria-label="`纸品单位 ${index + 1}`" :disabled="disabled || identityLocked" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2"><option v-if="unit && !unitOptions.includes(unit)">{{ unit }}</option><option v-for="value in unitOptions" :key="value">{{ value }}</option></select><input v-else v-model="unit" :aria-label="`纸品单位 ${index + 1}`" :disabled="disabled || identityLocked" required class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2"></label>
      <button type="button" :disabled="disabled || removeDisabled || identityLocked" :aria-label="`删除纸品明细 ${index + 1}`" class="mt-[22px] flex size-9 items-center justify-center justify-self-end rounded-lg border border-slate-200 bg-white text-slate-400 hover:border-red-200 hover:text-red-600 disabled:opacity-40" @click="emit('remove')"><X class="size-4" /></button>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.carton-paper-editor { container-type: inline-size; }
.carton-paper-fields { grid-template-columns: minmax(0, 1fr); }
@container (min-width: 360px) {
  .carton-paper-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .carton-paper-specification { grid-column: 1 / -1; }
}
@container (min-width: 880px) {
  .carton-paper-fields { grid-template-columns: minmax(0,1fr) minmax(0,1fr) minmax(0,1.7fr) minmax(0,1fr) minmax(0,1.1fr) 5rem 2.25rem; }
  .carton-paper-specification { grid-column: auto; }
}
</style>

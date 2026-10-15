<script setup lang="ts">
import { computed } from 'vue'
import { dimensionLabel, dimensionReference } from '@/features/carton-procurement/paperCatalog'
const props = defineProps<{ specification: string; label: string; disabled?: boolean; readonly?: boolean; showReference?: boolean; preferredUnit?: 'cm' | 'inch' | 'mm' }>()
const unit = defineModel<string>({ required: true })
const shortUnit = computed(() => ({ cm: 'cm', inch: '英寸', in: '英寸', mm: 'mm' })[unit.value.trim().toLowerCase()] || '')
const reference = computed(() => dimensionReference(props.specification, unit.value, props.readonly ? props.preferredUnit : undefined))
const warning = computed(() => !shortUnit.value ? '原单位待核实，请在基础资料补齐后重新选用包装。'
  : reference.value.includes('请核对') ? reference.value : '')
const convertedReference = computed(() => props.showReference && props.preferredUnit
  && (unit.value.trim().toLowerCase() === 'in' ? 'inch' : unit.value.trim().toLowerCase()) !== props.preferredUnit
  && reference.value.endsWith('（换算参考）') ? reference.value.replace('inch', '英寸') : '')
</script>
<template>
  <div class="space-y-1 text-xs" :aria-label="readonly ? label : undefined">
    <label v-if="!readonly" class="flex items-center gap-2">尺寸单位 *
      <select v-model="unit" :aria-label="label" :disabled="disabled" class="h-9 rounded-lg border border-teal-200 bg-white px-2 disabled:bg-slate-100">
        <option value="">请选择尺寸单位</option><option value="cm">厘米（cm）</option><option value="inch">英寸（inch）</option><option value="mm">毫米（mm）</option><option v-if="unit && !['cm', 'inch', 'mm'].includes(unit)" :value="unit">{{ dimensionLabel(unit) }}</option>
      </select>
    </label>
    <template v-if="readonly">
      <span v-if="shortUnit" class="text-slate-600" :title="reference">{{ shortUnit }}</span>
      <span v-if="convertedReference" class="ml-2 text-teal-700">{{ convertedReference }}</span>
      <p v-if="warning" class="text-amber-700">{{ warning }}</p>
    </template>
    <template v-else>
      <p class="font-semibold text-teal-800">原尺寸：{{ specification || '待填写' }} · {{ dimensionLabel(unit) }}</p>
      <p class="text-slate-500">{{ reference }}</p>
    </template>
  </div>
</template>

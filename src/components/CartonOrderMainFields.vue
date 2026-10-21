<script setup lang="ts">
defineProps<{ kind?: string; dueDate?: string; disabled?: boolean; typeLocked?: boolean }>()
const emit = defineEmits<{ 'update:kind': [value: string]; 'update:dueDate': [value: string] }>()
</script>
<template>
  <section aria-label="订单资料">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3 text-[11px]"><h4 class="font-bold text-slate-900">订单资料</h4><slot name="display" /></div>
    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <slot name="customer" />
      <label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">纸箱供应商</span><input value="河源东康纸品有限公司（系统固定）" aria-label="纸箱供应商" disabled class="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-slate-500"></label>
      <label v-if="kind && kind !== 'PURCHASE'" class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">订单类型</span><select :value="kind" :disabled="disabled || typeLocked" aria-label="申请类型" class="h-10 w-full rounded-lg border border-slate-200 px-3" @change="emit('update:kind', ($event.target as HTMLSelectElement).value)"><option value="SAMPLE">样板</option><option value="WORKSHOP_MISC">杂单</option><option v-if="kind === 'SUPPLIER_GIFT'" value="SUPPLIER_GIFT">供应商赠送</option></select></label>
      <slot />
      <slot name="dates"><label class="space-y-1.5"><span class="text-[11px] font-bold text-slate-600">计划交期 *</span><input :value="dueDate" aria-label="需求日期" type="date" required :disabled="disabled" class="h-10 w-full rounded-lg border border-slate-200 px-3" @input="emit('update:dueDate', ($event.target as HTMLInputElement).value)"></label></slot>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{ modelValue: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
<template>
  <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">订单备注（选填）</span><textarea :value="modelValue" :disabled="disabled" aria-label="订单备注" rows="3" maxlength="2000" placeholder="备注或特殊交付要求" class="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-teal-500" @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)" /></label>
</template>

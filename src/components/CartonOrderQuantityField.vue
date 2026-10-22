<script setup lang="ts">
withDefaults(defineProps<{ modelValue?: string | number | null; index: number; disabled?: boolean; calculated?: boolean; manual?: boolean }>(), { calculated: false })
const emit = defineEmits<{ 'update:modelValue': [value: string]; restore: [] }>()
</script>
<template>
  <div class="min-w-0 space-y-1.5">
    <div class="flex items-center justify-between gap-1 text-[11px] leading-4"><span class="whitespace-nowrap font-bold text-slate-500">{{ calculated ? '纸品数量' : '纸品需求数量 *' }}</span><span v-if="calculated" class="shrink-0 text-[10px] text-teal-700">{{ manual ? '手动' : '自动' }}</span></div>
    <input :value="modelValue" :aria-label="`${calculated ? '纸箱数量' : '纸品需求数量'} ${index + 1}`" type="number" min="0.0001" step="0.0001" required :disabled="disabled" class="h-9 w-full rounded-lg border border-teal-200 bg-teal-50 px-2 text-right font-bold text-teal-700" @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)">
    <button v-if="calculated && manual" type="button" :disabled="disabled" class="block text-[11px] text-teal-700 underline" @click="emit('restore')">恢复自动</button>
  </div>
</template>

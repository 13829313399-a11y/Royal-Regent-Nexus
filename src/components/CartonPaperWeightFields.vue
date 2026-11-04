<script setup lang="ts">
defineProps<{ net?: string | number | null; gross?: string | number | null; index: number; disabled?: boolean; prefix?: string }>()
const emit = defineEmits<{ 'update:net': [value: number | null]; 'update:gross': [value: number | null] }>()
const value = (event: Event) => { const raw = (event.target as HTMLInputElement).value; return raw === '' ? null : Number(raw) }
</script>
<template>
  <div class="grid gap-3 sm:grid-cols-2">
    <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">每箱净重（kg，选填）</span><input :value="net" :aria-label="`${prefix || '纸品'}每箱净重 ${index + 1}`" :disabled="disabled" type="number" min="0" step="0.0001" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 disabled:bg-slate-100" @input="emit('update:net', value($event))"></label>
    <label class="space-y-1.5"><span class="text-[10px] font-bold text-slate-500">每箱毛重（kg，选填）</span><input :value="gross" :aria-label="`${prefix || '纸品'}每箱毛重 ${index + 1}`" :disabled="disabled" type="number" min="0" step="0.0001" class="h-9 w-full rounded-lg border border-slate-200 bg-white px-2 disabled:bg-slate-100" @input="emit('update:gross', value($event))"></label>
  </div>
</template>

<script setup lang="ts">
defineProps<{ fields: { label: string; value: string | number | null | undefined; tone?: string; wide?: boolean }[] }>()
</script>
<template>
  <section aria-label="订单资料" class="grid gap-x-5 gap-y-3 rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-[12px] sm:grid-cols-2 lg:grid-cols-4">
    <div v-for="field in fields" :key="field.label" class="min-w-0" :class="field.wide ? 'sm:col-span-2 lg:col-span-4' : ''"><span class="text-slate-500">{{ field.label }}</span><b class="ml-2 whitespace-pre-wrap break-words tabular-nums" :class="field.tone || 'text-slate-900'">{{ field.value === '' || field.value == null ? '—' : field.value }}</b></div>
  </section>
</template>

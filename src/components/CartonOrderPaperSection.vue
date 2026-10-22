<script setup lang="ts">
import { Plus } from '@lucide/vue'
defineProps<{ disabled?: boolean; guidance?: string }>()
const emit = defineEmits<{ add: [] }>()
</script>
<template>
  <section class="rounded-xl border border-slate-200" aria-label="纸品明细">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3">
      <div><h4 class="font-bold text-slate-950">纸品明细</h4><p v-if="guidance" class="mt-2 text-xs text-slate-500">{{ guidance }}</p><slot name="help" /></div>
      <button type="button" :disabled="disabled" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-teal-200 bg-white px-3 text-[11px] font-bold text-teal-700 disabled:opacity-40" @click="emit('add')"><Plus class="size-3.5" />新增纸品明细</button>
    </div>
    <div class="space-y-3 p-4"><slot /></div>
  </section>
</template>

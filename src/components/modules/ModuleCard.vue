<script setup lang="ts">
import { RouterLink } from 'vue-router'
import type { EnterpriseModule, Tone } from '@/data/enterpriseMock'
import StatusPill from '@/components/common/StatusPill.vue'

defineProps<{
  module: EnterpriseModule
}>()

const iconClasses: Record<Tone, string> = {
  teal: 'bg-teal-50 text-teal-700',
  blue: 'bg-blue-50 text-blue-700',
  amber: 'bg-amber-50 text-amber-700',
  red: 'bg-red-50 text-red-700',
  slate: 'bg-slate-100 text-slate-700',
  green: 'bg-emerald-50 text-emerald-700',
}
</script>

<template>
  <component
    :is="module.to ? RouterLink : 'article'"
    :to="module.to"
    class="block rounded-lg border border-slate-200 bg-slate-50 p-5 transition-colors"
    :class="module.to ? 'hover:border-teal-300 hover:bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700' : ''"
  >
    <div class="mb-5 flex items-start gap-4">
      <span
        class="flex size-10 shrink-0 items-center justify-center rounded-xl"
        :class="iconClasses[module.statusTone]"
      >
        <component :is="module.icon" class="size-5" aria-hidden="true" />
      </span>
      <div class="min-w-0">
        <h3 class="truncate font-semibold text-slate-950">{{ module.title }}</h3>
        <p class="mt-1 text-xs text-slate-500">{{ module.owner }}</p>
      </div>
    </div>
    <p class="min-h-10 text-sm leading-6 text-slate-700">{{ module.summary }}</p>
    <div class="mt-4 flex items-center justify-between gap-3">
      <StatusPill :label="module.status" :tone="module.statusTone" compact />
      <span class="text-xs text-slate-500">{{ module.stats }}</span>
    </div>
  </component>
</template>

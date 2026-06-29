<script setup lang="ts">
import { ArrowUpRight, ChevronRight } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import type { EnterpriseModule, Tone } from '@/data/enterpriseMock'
import StatusPill from '@/components/common/StatusPill.vue'

defineProps<{
  module: EnterpriseModule
  active?: boolean
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
  <article
    class="rounded-lg border p-5 transition-colors"
    :class="active
      ? 'border-teal-300 bg-white shadow-[0_12px_32px_rgba(13,148,136,0.12)]'
      : 'border-slate-200 bg-slate-50'"
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
    <div class="mt-4 grid gap-3 sm:grid-cols-3">
      <div
        v-for="metric in module.statusMetrics"
        :key="`${module.id}-${metric.label}`"
        class="rounded-lg border border-slate-200 bg-white px-3 py-2"
      >
        <p class="text-[11px] uppercase tracking-wide text-slate-500">{{ metric.label }}</p>
        <p
          class="mt-1 text-sm font-semibold"
          :class="{
            'text-teal-700': metric.tone === 'teal',
            'text-blue-700': metric.tone === 'blue',
            'text-amber-700': metric.tone === 'amber',
            'text-red-700': metric.tone === 'red',
            'text-slate-700': metric.tone === 'slate',
            'text-emerald-700': metric.tone === 'green',
          }"
        >
          {{ metric.value }}
        </p>
      </div>
    </div>
    <div class="mt-4 flex flex-wrap gap-2">
      <span
        v-for="child in module.children.slice(0, 3)"
        :key="`${module.id}-${child.label}`"
        class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600"
      >
        {{ child.label }}
      </span>
    </div>
    <div class="mt-4 flex items-center justify-between gap-3">
      <StatusPill :label="module.status" :tone="module.statusTone" compact />
      <span class="text-xs text-slate-500">{{ module.stats }}</span>
    </div>
    <div class="mt-5 flex flex-wrap items-center gap-3">
      <RouterLink
        v-if="module.route"
        :to="module.route"
        class="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white"
      >
        查看模块
        <ChevronRight class="size-4" aria-hidden="true" />
      </RouterLink>
      <a
        v-if="module.href"
        :href="module.href"
        target="_blank"
        rel="noreferrer"
        class="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700"
      >
        打开系统
        <ArrowUpRight class="size-4" aria-hidden="true" />
      </a>
    </div>
  </article>
</template>

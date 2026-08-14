<script setup lang="ts">
import { ShieldCheck } from '@lucide/vue'
import type { AISourceSummary } from '@/features/ai-assistant/types'

defineProps<{ sources: AISourceSummary[] }>()

const factoryLabels: Record<string, string> = {
  'huakang-a': '华康 A', 'huakang-b': '华康 B', 'huakang-c': '华康 C',
  'huakang-d': '华康 D', huadeng: '华登', huaxing: '华兴',
}

function sourceHref(route: string, query?: Record<string, string>) {
  const encoded = new URLSearchParams(query ?? {}).toString()
  return encoded ? `${route}?${encoded}` : route
}
</script>

<template>
  <section v-if="sources.length" class="mx-4 mt-3 rounded-xl border border-slate-200 bg-white p-3 sm:mx-5" aria-label="回答来源">
    <div class="flex items-center gap-2 text-xs font-semibold text-slate-800">
      <ShieldCheck class="size-4 text-emerald-600" aria-hidden="true" />
      回答来源
    </div>
    <ul class="mt-2 space-y-2">
      <li v-for="source in sources" :key="source.id" class="text-[11px] leading-5 text-slate-600">
        <span class="font-medium text-slate-700">{{ source.label }}</span>
        <span v-if="source.factoryId"> · {{ factoryLabels[source.factoryId] ?? source.factoryId }}</span>
        <span v-if="source.updatedAt"> · {{ source.updatedAt }}</span>
        <span v-if="source.links.length" class="ml-2 inline-flex flex-wrap gap-1.5">
          <a
            v-for="link in source.links"
            :key="`${link.route}:${link.label}`"
            :href="sourceHref(link.route, link.query)"
            class="font-semibold text-sky-700 underline decoration-sky-300 underline-offset-2"
          >{{ link.label }}</a>
        </span>
      </li>
    </ul>
  </section>
</template>
